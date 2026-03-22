"""
Pydantic request/response schemas for campaign API endpoints.

These schemas are shared across campaign route modules:
  - campaigns.py (CRUD and user-profile routes)
  - campaign_members.py (member management routes)
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

from backend.models.campaign import CampaignBrief, ChannelType, SocialMediaPlatform
from backend.models.user_settings import UITheme
from backend.apps.api.schemas.common import PaginationMeta


# ---------------------------------------------------------------------------
# Member-management request / response models
# ---------------------------------------------------------------------------

class AddMemberRequest(BaseModel):
    user_id: str
    role: Literal["editor", "viewer"] = "viewer"


class UpdateMemberRoleRequest(BaseModel):
    role: Literal["editor", "viewer"]


class CampaignMemberResponse(BaseModel):
    campaign_id: str
    user_id: str
    role: str
    added_at: datetime


# ---------------------------------------------------------------------------
# Campaign response DTOs
# ---------------------------------------------------------------------------

class CreateCampaignResponse(BaseModel):
    id: str
    status: str
    message: str


class CampaignSummary(BaseModel):
    id: str
    status: str
    product_or_service: str
    goal: str
    owner_id: Optional[str]
    workspace_id: Optional[str]
    workspace_name: Optional[str]
    created_at: datetime
    updated_at: datetime
    wizard_step: int = 0


class CampaignListResponse(BaseModel):
    items: list[CampaignSummary]
    pagination: PaginationMeta


class CreateCampaignRequest(CampaignBrief):
    """Request body for campaign creation.

    workspace_id is now a required URL path parameter; it is no longer
    accepted in the request body.
    """


class UpdateDraftRequest(BaseModel):
    """Partial-update request body for PATCH /campaigns/{id}.

    All fields are optional; only provided fields are applied to the draft.
    """

    product_or_service: Optional[str] = None
    goal: Optional[str] = None
    budget: Optional[float] = None
    currency: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    additional_context: Optional[str] = None
    selected_channels: Optional[list[ChannelType]] = None
    social_media_platforms: Optional[list[SocialMediaPlatform]] = None
    wizard_step: Optional[int] = None


class AssignWorkspaceRequest(BaseModel):
    """Request body for PATCH /api/campaigns/{id}/workspace."""

    workspace_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Me response model
# ---------------------------------------------------------------------------

class MeResponse(BaseModel):
    id: str
    email: Optional[str]
    display_name: Optional[str]
    roles: list[str]
    is_admin: bool
    can_build: bool
    is_viewer: bool


_LOCALE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z]{2})?$")


def _normalize_locale(locale: str) -> str:
    parts = locale.split("-")
    if len(parts) == 1:
        return parts[0].lower()
    return f"{parts[0].lower()}-{parts[1].upper()}"


class MeSettingsResponse(BaseModel):
    theme: UITheme = UITheme.SYSTEM
    locale: str = "en-US"
    timezone: str = "UTC"
    default_workspace_id: Optional[str] = None
    notification_prefs: dict[str, Any] = Field(default_factory=dict)
    dashboard_prefs: dict[str, Any] = Field(default_factory=dict)


class PatchMeSettingsRequest(BaseModel):
    theme: UITheme | None = None
    locale: str | None = None
    timezone: str | None = None
    default_workspace_id: str | None = None
    notification_prefs: dict[str, Any] | None = None
    dashboard_prefs: dict[str, Any] | None = None

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not _LOCALE_PATTERN.fullmatch(value):
            raise ValueError("Invalid locale format. Expected language or language-region (e.g. en-US).")
        return _normalize_locale(value)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Invalid timezone.") from exc
        return value
