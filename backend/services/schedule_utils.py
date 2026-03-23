"""
Schedule utilities — pure functions for heuristic schedule seeding and validation.

No LLM dependency; safe to use as a deterministic fallback and as a validation
layer for schedules produced by agents or set manually by users.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from backend.models.campaign import ChannelPlan, ContentPiece


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CadenceSpec:
    """Parsed cadence extracted from a Channel Planner timing string."""

    frequency_per_week: float
    phases: list[dict] | None = field(default=None)
    # phases example: [{"weeks": 2, "freq": 5}, {"weeks": None, "freq": 2}]


@dataclass
class ScheduleViolation:
    """A single schedule constraint violation."""

    piece_index: int
    field: str
    message: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Patterns ordered from most-specific to least-specific
_DAILY_RE = re.compile(r"\bdaily\b", re.IGNORECASE)
_NX_WEEK_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[xX×]\s*(?:per\s+)?/?week", re.IGNORECASE)
_N_PER_WEEK_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s+(?:posts?|times?|emails?|pieces?|articles?)\s+per\s+week",
    re.IGNORECASE,
)
_WEEKLY_RE = re.compile(r"\bweekly\b", re.IGNORECASE)
_BIWEEKLY_RE = re.compile(r"\bbi[\-\s]?weekly\b", re.IGNORECASE)
_MONTHLY_RE = re.compile(r"\bmonthly\b", re.IGNORECASE)

# Phased patterns like "launch week 1-2, then bi-weekly" or "burst then sustain"
_PHASE_SEP_RE = re.compile(r"\bthen\b", re.IGNORECASE)
_LAUNCH_WEEKS_RE = re.compile(r"(?:launch\s+)?week\s*(\d+)[\s\-–]+(\d+)", re.IGNORECASE)


def _freq_from_segment(segment: str) -> Optional[float]:
    """Return frequency-per-week from a single timing segment, or None."""
    if _DAILY_RE.search(segment):
        return 7.0
    m = _NX_WEEK_RE.search(segment)
    if m:
        return float(m.group(1))
    m = _N_PER_WEEK_RE.search(segment)
    if m:
        return float(m.group(1))
    if _BIWEEKLY_RE.search(segment):
        return 0.5
    if _WEEKLY_RE.search(segment):
        return 1.0
    if _MONTHLY_RE.search(segment):
        return 7.0 / 30.0  # ≈ 0.233
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_cadence(timing: str) -> Optional[CadenceSpec]:
    """Parse a Channel Planner timing string into a :class:`CadenceSpec`.

    Returns ``None`` for unrecognisable text so that callers can leave the
    piece unscheduled without crashing.
    """
    if not timing or not timing.strip():
        return None

    # Check for phased patterns first (contains "then")
    if _PHASE_SEP_RE.search(timing):
        parts = _PHASE_SEP_RE.split(timing, maxsplit=1)
        before = parts[0].strip()
        after = parts[1].strip() if len(parts) > 1 else ""

        freq_before = _freq_from_segment(before)
        freq_after = _freq_from_segment(after)

        # Try to extract the number of weeks for the initial phase
        weeks_before: int | None = None
        m = _LAUNCH_WEEKS_RE.search(before)
        if m:
            # e.g. "week 1-2" → 2 weeks
            weeks_before = int(m.group(2))
            # "Launch week 1-2" with no explicit frequency implies a daily burst
            if freq_before is None:
                freq_before = 7.0

        # We need at least one recognisable frequency to form a spec
        if freq_before is None and freq_after is None:
            return None

        phases: list[dict] = []
        if freq_before is not None:
            phases.append({"weeks": weeks_before, "freq": freq_before})
        if freq_after is not None:
            phases.append({"weeks": None, "freq": freq_after})

        # Primary frequency is the first phase's freq (or fall back to the second)
        primary_freq = (freq_before if freq_before is not None else freq_after)
        return CadenceSpec(frequency_per_week=primary_freq, phases=phases)  # type: ignore[arg-type]

    # Non-phased: pick the first recognisable frequency in the string
    freq = _freq_from_segment(timing)
    if freq is None:
        return None
    return CadenceSpec(frequency_per_week=freq)


def seed_schedule(
    pieces: list[ContentPiece],
    channel_plan: ChannelPlan,
    start_date: date,
    end_date: date,
) -> list[ContentPiece]:
    """Distribute *pieces* across the campaign date range using cadence data
    from *channel_plan*.

    Each piece is matched to its :class:`ChannelRecommendation` via
    ``piece.channel``.  Pieces whose channel has no matching recommendation, or
    whose timing text cannot be parsed, are left with ``scheduled_date=None``.

    ``platform_target`` is set from the recommendation's ``platform_breakdown``
    when available (round-robin across platforms by piece order within the
    channel).

    The function returns a **new list of copied pieces** — original objects are
    not mutated.
    """
    if start_date > end_date:
        return [p.model_copy() for p in pieces]

    # Build lookup: channel name → ChannelRecommendation
    rec_by_channel: dict[str, object] = {
        rec.channel.value: rec for rec in channel_plan.recommendations
    }

    # Group pieces by channel to distribute dates independently per channel
    channel_pieces: dict[str, list[tuple[int, ContentPiece]]] = defaultdict(list)
    for idx, piece in enumerate(pieces):
        channel_pieces[piece.channel].append((idx, piece))

    result: list[Optional[ContentPiece]] = [None] * len(pieces)

    for channel, indexed_pieces in channel_pieces.items():
        rec = rec_by_channel.get(channel)
        if rec is None:
            # No recommendation → leave unscheduled
            for orig_idx, piece in indexed_pieces:
                result[orig_idx] = piece.model_copy()
            continue

        cadence = parse_cadence(rec.timing)  # type: ignore[attr-defined]
        if cadence is None:
            # Unparseable timing → leave unscheduled
            for orig_idx, piece in indexed_pieces:
                result[orig_idx] = piece.model_copy()
            continue

        # Determine platform targets for this channel (round-robin)
        platform_targets: list[Optional[str]] = [None]
        if rec.platform_breakdown:  # type: ignore[attr-defined]
            platform_targets = [pb.platform for pb in rec.platform_breakdown]  # type: ignore[attr-defined]

        # Compute candidate publish dates from cadence
        dates = _generate_dates(cadence, start_date, end_date, len(indexed_pieces))

        for position, (orig_idx, piece) in enumerate(indexed_pieces):
            copy = piece.model_copy()
            if position < len(dates):
                copy.scheduled_date = dates[position]
            # Assign platform target (round-robin)
            copy.platform_target = platform_targets[position % len(platform_targets)]
            result[orig_idx] = copy

    # Fill any None slots (shouldn't happen, but be safe)
    for i, piece in enumerate(pieces):
        if result[i] is None:
            result[i] = piece.model_copy()

    return result  # type: ignore[return-value]


def _generate_dates(
    cadence: CadenceSpec,
    start_date: date,
    end_date: date,
    n_pieces: int,
) -> list[date]:
    """Return up to *n_pieces* evenly-spaced dates within [start_date, end_date]
    that respect the cadence's frequency_per_week.
    """
    if cadence.phases:
        # Use phased approach: fill the burst phase first, then sustain
        dates: list[date] = []
        cursor = start_date
        for phase in cadence.phases:
            if len(dates) >= n_pieces:
                break
            freq = phase.get("freq") or cadence.frequency_per_week
            phase_weeks = phase.get("weeks")
            if phase_weeks:
                phase_end = min(
                    start_date + timedelta(weeks=phase_weeks) - timedelta(days=1),
                    end_date,
                )
            else:
                phase_end = end_date

            phase_dates = _spread_dates(freq, cursor, phase_end, n_pieces - len(dates))
            dates.extend(phase_dates)
            cursor = phase_end + timedelta(days=1)
            if cursor > end_date:
                break
        return dates[:n_pieces]

    return _spread_dates(cadence.frequency_per_week, start_date, end_date, n_pieces)


def _spread_dates(
    freq_per_week: float,
    start: date,
    end: date,
    n: int,
) -> list[date]:
    """Return up to *n* dates between *start* and *end* spaced at *freq_per_week*."""
    if n <= 0 or freq_per_week <= 0:
        return []
    total_days = (end - start).days + 1
    if total_days <= 0:
        return []

    # Interval between posts in days
    interval_days = max(1, round(7.0 / freq_per_week))

    dates: list[date] = []
    current = start
    while current <= end and len(dates) < n:
        dates.append(current)
        current += timedelta(days=interval_days)

    return dates


def validate_schedule(
    pieces: list[ContentPiece],
    start_date: date,
    end_date: date,
) -> list[ScheduleViolation]:
    """Validate *pieces* against campaign date-range and conflict constraints.

    Returns a (possibly empty) list of :class:`ScheduleViolation` objects.
    An empty list means the schedule is valid.

    Checks performed:
    - Each scheduled date falls within [start_date, end_date].
    - No two pieces share the same ``platform_target`` and ``scheduled_date``
      (same-platform same-day conflict).
    """
    violations: list[ScheduleViolation] = []

    # Accumulate (platform, date) → first seen piece_index for conflict detection
    seen: dict[tuple[str, date], int] = {}

    for idx, piece in enumerate(pieces):
        if piece.scheduled_date is None:
            continue

        # Range check
        if piece.scheduled_date < start_date:
            violations.append(
                ScheduleViolation(
                    piece_index=idx,
                    field="scheduled_date",
                    message=(
                        f"scheduled_date {piece.scheduled_date} is before campaign "
                        f"start {start_date}"
                    ),
                )
            )
        elif piece.scheduled_date > end_date:
            violations.append(
                ScheduleViolation(
                    piece_index=idx,
                    field="scheduled_date",
                    message=(
                        f"scheduled_date {piece.scheduled_date} is after campaign "
                        f"end {end_date}"
                    ),
                )
            )

        # Conflict check (only when platform_target is set)
        if piece.platform_target:
            key = (piece.platform_target, piece.scheduled_date)
            if key in seen:
                violations.append(
                    ScheduleViolation(
                        piece_index=idx,
                        field="scheduled_date",
                        message=(
                            f"same-platform/same-day conflict with piece "
                            f"{seen[key]}: platform '{piece.platform_target}' "
                            f"on {piece.scheduled_date}"
                        ),
                    )
                )
            else:
                seen[key] = idx

    return violations
