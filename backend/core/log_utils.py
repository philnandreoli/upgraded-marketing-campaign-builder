"""
Centralized logging utilities for the marketing campaign backend.

Policy: campaign free-text fields (user-supplied brief content) must never
appear in log output.  Only metadata such as ``campaign_id``,
``workspace_id``, actor, status, and timestamps may be logged.

Usage::

    from backend.core.log_utils import redact_brief, safe_campaign_context

    # Redact a CampaignBrief dict before logging
    logger.info("Creating campaign context=%s", safe_campaign_context(...))
"""

from __future__ import annotations

from typing import Any

# Free-text fields on CampaignBrief that may contain sensitive business
# information and must never be logged in plaintext.
SENSITIVE_BRIEF_FIELDS: frozenset[str] = frozenset(
    {
        "product_or_service",
        "goal",
        "additional_context",
    }
)


def redact_brief(brief_dict: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *brief_dict* with sensitive free-text fields replaced
    by the string ``"[REDACTED]"``.

    Non-sensitive metadata fields (``budget``, ``currency``, ``start_date``,
    ``end_date``, ``selected_channels``, ``social_media_platforms``) are
    preserved so that logs retain enough context for debugging.

    Args:
        brief_dict: A dict representation of a :class:`~backend.models.campaign.CampaignBrief`.

    Returns:
        A new dict with sensitive fields replaced by ``"[REDACTED]"``.
    """
    return {
        key: "[REDACTED]" if key in SENSITIVE_BRIEF_FIELDS else value
        for key, value in brief_dict.items()
    }


def safe_campaign_context(
    *,
    campaign_id: str | None = None,
    workspace_id: str | None = None,
    actor: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Return a metadata-only dict suitable for structured log messages.

    This helper enforces the allowlist logging policy: only non-sensitive
    identifiers and status values are included; no free-text fields are
    ever present in the returned dict.

    Args:
        campaign_id: The campaign UUID.
        workspace_id: The workspace UUID.
        actor: The user ID or ``"anonymous"`` performing the action.
        status: The campaign status string.

    Returns:
        A dict with only the provided non-``None`` values.
    """
    ctx: dict[str, Any] = {}
    if campaign_id is not None:
        ctx["campaign_id"] = campaign_id
    if workspace_id is not None:
        ctx["workspace_id"] = workspace_id
    if actor is not None:
        ctx["actor"] = actor
    if status is not None:
        ctx["status"] = status
    return ctx
