"""
Tests for backend/services/schedule_utils.py

Covers:
- parse_cadence() with ~10 timing string variants
- seed_schedule() with known inputs and verified date outputs
- validate_schedule() with valid/invalid date combinations
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import pytest

from backend.models.campaign import (
    ChannelPlan,
    ChannelRecommendation,
    ChannelType,
    ContentPiece,
    PlatformBreakdown,
)
from backend.services.schedule_utils import (
    CadenceSpec,
    ScheduleViolation,
    parse_cadence,
    seed_schedule,
    validate_schedule,
)


# ---------------------------------------------------------------------------
# parse_cadence — parametrized
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "timing, expected_freq, expected_phases_len",
    [
        # daily
        ("daily", 7.0, None),
        ("Daily posts", 7.0, None),
        # Nx/week variants
        ("3x/week", 3.0, None),
        ("3x per week", 3.0, None),
        ("3X/week", 3.0, None),
        # "N posts per week" variants
        ("2 posts per week", 2.0, None),
        ("5 times per week", 5.0, None),
        # weekly
        ("weekly", 1.0, None),
        ("Weekly newsletter", 1.0, None),
        # bi-weekly
        ("bi-weekly", 0.5, None),
        ("Bi-Weekly updates", 0.5, None),
        ("biweekly", 0.5, None),
        # monthly
        ("monthly", pytest.approx(7.0 / 30.0, rel=0.01), None),
        # phased: "launch week 1-2, then bi-weekly"
        ("Launch week 1-2, then bi-weekly", 7.0, 2),
        # phased: "burst then weekly"
        ("3x/week then weekly", 3.0, 2),
        # daily stories in compound string (picks first match)
        ("Daily posts, 3x Stories per week", 7.0, None),
        # unrecognisable → None
        ("TBD", None, None),
        ("", None, None),
        ("   ", None, None),
        ("negotiate timing later", None, None),
    ],
)
def test_parse_cadence(
    timing: str,
    expected_freq: Optional[float],
    expected_phases_len: Optional[int],
) -> None:
    result = parse_cadence(timing)
    if expected_freq is None:
        assert result is None, f"Expected None for '{timing}', got {result}"
    else:
        assert result is not None, f"Expected CadenceSpec for '{timing}', got None"
        assert result.frequency_per_week == expected_freq
        if expected_phases_len is None:
            assert result.phases is None or result.phases == []
        else:
            assert result.phases is not None
            assert len(result.phases) == expected_phases_len


def test_parse_cadence_phased_structure() -> None:
    """Verify phase dict structure for a well-known phased timing string."""
    result = parse_cadence("Launch week 1-2, then bi-weekly")
    assert result is not None
    assert result.phases is not None
    assert len(result.phases) == 2
    burst, sustain = result.phases
    assert burst["weeks"] == 2
    assert burst["freq"] == pytest.approx(7.0)
    assert sustain["weeks"] is None
    assert sustain["freq"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# seed_schedule — helpers
# ---------------------------------------------------------------------------

def _make_piece(channel: str, content: str = "test") -> ContentPiece:
    return ContentPiece(content_type="social_post", channel=channel, content=content)


def _make_plan(
    channel: str,
    timing: str,
    platforms: list[str] | None = None,
) -> ChannelPlan:
    breakdown = (
        [PlatformBreakdown(platform=p, budget_pct=100.0 / len(platforms)) for p in platforms]
        if platforms
        else None
    )
    rec = ChannelRecommendation(
        channel=ChannelType(channel),
        timing=timing,
        platform_breakdown=breakdown,
    )
    return ChannelPlan(recommendations=[rec])


# ---------------------------------------------------------------------------
# seed_schedule — tests
# ---------------------------------------------------------------------------

class TestSeedSchedule:
    START = date(2026, 4, 1)
    END = date(2026, 4, 30)  # 30-day window

    def test_daily_cadence_assigns_dates(self) -> None:
        pieces = [_make_piece("social_media") for _ in range(3)]
        plan = _make_plan("social_media", "daily")
        result = seed_schedule(pieces, plan, self.START, self.END)
        assert len(result) == 3
        # All pieces should receive a scheduled date
        for p in result:
            assert p.scheduled_date is not None
            assert self.START <= p.scheduled_date <= self.END

    def test_weekly_cadence_spreads_pieces(self) -> None:
        pieces = [_make_piece("email") for _ in range(4)]
        plan = _make_plan("email", "weekly")
        result = seed_schedule(pieces, plan, self.START, self.END)
        dates = [p.scheduled_date for p in result if p.scheduled_date]
        # 4 pieces weekly over 30 days → 4 dates, each ~7 days apart
        assert len(dates) == 4
        for i in range(1, len(dates)):
            gap = (dates[i] - dates[i - 1]).days
            assert gap == 7, f"Expected 7-day gap, got {gap}"

    def test_platform_target_set_from_breakdown(self) -> None:
        pieces = [_make_piece("social_media") for _ in range(4)]
        plan = _make_plan("social_media", "2 posts per week", platforms=["instagram", "linkedin"])
        result = seed_schedule(pieces, plan, self.START, self.END)
        platforms = [p.platform_target for p in result]
        # round-robin: instagram, linkedin, instagram, linkedin
        assert platforms == ["instagram", "linkedin", "instagram", "linkedin"]

    def test_no_matching_recommendation_leaves_unscheduled(self) -> None:
        pieces = [_make_piece("seo")]
        plan = _make_plan("email", "weekly")  # no seo recommendation
        result = seed_schedule(pieces, plan, self.START, self.END)
        assert result[0].scheduled_date is None

    def test_unparseable_timing_leaves_unscheduled(self) -> None:
        pieces = [_make_piece("pr")]
        plan = _make_plan("pr", "TBD")
        result = seed_schedule(pieces, plan, self.START, self.END)
        assert result[0].scheduled_date is None

    def test_original_pieces_not_mutated(self) -> None:
        pieces = [_make_piece("email")]
        plan = _make_plan("email", "weekly")
        result = seed_schedule(pieces, plan, self.START, self.END)
        assert pieces[0].scheduled_date is None  # original untouched
        assert result[0].scheduled_date is not None

    def test_inverted_date_range_returns_copies(self) -> None:
        pieces = [_make_piece("email")]
        plan = _make_plan("email", "weekly")
        # start > end is invalid — should return copies without crashing
        result = seed_schedule(pieces, plan, self.END, self.START)
        assert len(result) == 1
        assert result[0].scheduled_date is None

    def test_multiple_channels_independent(self) -> None:
        email_pieces = [_make_piece("email"), _make_piece("email")]
        social_pieces = [_make_piece("social_media"), _make_piece("social_media")]
        all_pieces = email_pieces + social_pieces
        plan = ChannelPlan(
            recommendations=[
                ChannelRecommendation(channel=ChannelType.EMAIL, timing="weekly"),
                ChannelRecommendation(channel=ChannelType.SOCIAL_MEDIA, timing="3x/week"),
            ]
        )
        result = seed_schedule(all_pieces, plan, self.START, self.END)
        # All pieces should have dates
        for p in result:
            assert p.scheduled_date is not None

    def test_fewer_pieces_than_cadence_slots(self) -> None:
        """Single piece with daily cadence should still get exactly one date."""
        pieces = [_make_piece("social_media")]
        plan = _make_plan("social_media", "daily")
        result = seed_schedule(pieces, plan, self.START, self.END)
        assert result[0].scheduled_date == self.START

    def test_platform_target_none_when_no_breakdown(self) -> None:
        pieces = [_make_piece("email")]
        plan = _make_plan("email", "weekly", platforms=None)
        result = seed_schedule(pieces, plan, self.START, self.END)
        assert result[0].platform_target is None

    def test_phased_cadence_burst_then_sustain(self) -> None:
        """Pieces under a phased cadence should be distributed across both phases."""
        pieces = [_make_piece("paid_ads") for _ in range(5)]
        plan = _make_plan("paid_ads", "Launch week 1-2, then bi-weekly")
        result = seed_schedule(pieces, plan, self.START, self.END)
        scheduled = [p for p in result if p.scheduled_date is not None]
        assert len(scheduled) >= 1
        # All assigned dates within range
        for p in scheduled:
            assert self.START <= p.scheduled_date <= self.END


# ---------------------------------------------------------------------------
# validate_schedule — tests
# ---------------------------------------------------------------------------

class TestValidateSchedule:
    START = date(2026, 4, 1)
    END = date(2026, 4, 30)

    def _piece(
        self,
        scheduled_date: Optional[date] = None,
        platform: Optional[str] = None,
    ) -> ContentPiece:
        return ContentPiece(
            content_type="social_post",
            content="x",
            scheduled_date=scheduled_date,
            platform_target=platform,
        )

    def test_valid_schedule_returns_no_violations(self) -> None:
        pieces = [
            self._piece(date(2026, 4, 5), "instagram"),
            self._piece(date(2026, 4, 12), "instagram"),
            self._piece(date(2026, 4, 5), "linkedin"),  # different platform = OK
        ]
        violations = validate_schedule(pieces, self.START, self.END)
        assert violations == []

    def test_unscheduled_pieces_ignored(self) -> None:
        pieces = [self._piece(None, "instagram")]
        violations = validate_schedule(pieces, self.START, self.END)
        assert violations == []

    def test_date_before_start_flagged(self) -> None:
        pieces = [self._piece(date(2026, 3, 15), "instagram")]
        violations = validate_schedule(pieces, self.START, self.END)
        assert len(violations) == 1
        assert violations[0].piece_index == 0
        assert violations[0].field == "scheduled_date"
        assert "before campaign start" in violations[0].message

    def test_date_after_end_flagged(self) -> None:
        pieces = [self._piece(date(2026, 5, 5), "instagram")]
        violations = validate_schedule(pieces, self.START, self.END)
        assert len(violations) == 1
        assert violations[0].piece_index == 0
        assert "after campaign end" in violations[0].message

    def test_same_platform_same_day_conflict(self) -> None:
        pieces = [
            self._piece(date(2026, 4, 10), "instagram"),
            self._piece(date(2026, 4, 10), "instagram"),  # conflict
        ]
        violations = validate_schedule(pieces, self.START, self.END)
        assert len(violations) == 1
        assert violations[0].piece_index == 1
        assert "conflict" in violations[0].message.lower()
        assert "instagram" in violations[0].message

    def test_same_day_different_platforms_no_conflict(self) -> None:
        pieces = [
            self._piece(date(2026, 4, 10), "instagram"),
            self._piece(date(2026, 4, 10), "linkedin"),
        ]
        violations = validate_schedule(pieces, self.START, self.END)
        assert violations == []

    def test_multiple_violations_all_returned(self) -> None:
        pieces = [
            self._piece(date(2026, 3, 1), "instagram"),   # before start
            self._piece(date(2026, 5, 1), "linkedin"),    # after end
            self._piece(date(2026, 4, 10), "twitter"),
            self._piece(date(2026, 4, 10), "twitter"),   # conflict
        ]
        violations = validate_schedule(pieces, self.START, self.END)
        assert len(violations) == 3

    def test_boundary_dates_are_valid(self) -> None:
        pieces = [
            self._piece(self.START, "instagram"),
            self._piece(self.END, "instagram"),
        ]
        # Different days → no conflict; both within range → no violations
        violations = validate_schedule(pieces, self.START, self.END)
        assert violations == []

    def test_no_platform_target_skips_conflict_check(self) -> None:
        """Pieces without platform_target should not be compared for conflicts."""
        pieces = [
            self._piece(date(2026, 4, 10), None),
            self._piece(date(2026, 4, 10), None),
        ]
        violations = validate_schedule(pieces, self.START, self.END)
        assert violations == []
