"""
Pydantic request/response schemas for campaign API endpoints.

These schemas are shared across campaign route modules:
  - campaigns.py (CRUD and user-profile routes)
  - campaign_members.py (member management routes)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel

from backend.models.campaign import CampaignBrief, ChannelType, SocialMediaPlatform


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
    created_at: str
    updated_at: str
    wizard_step: int = 0


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
