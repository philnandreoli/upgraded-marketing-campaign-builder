"""
Pydantic request/response schemas for campaign API endpoints.

These schemas are shared across campaign route modules:
  - campaigns.py (CRUD and user-profile routes)
  - campaign_members.py (member management routes)
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from backend.models.campaign import CampaignBrief


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


class CreateCampaignRequest(CampaignBrief):
    """Request body for campaign creation.

    Extends CampaignBrief with an optional workspace_id to associate
    the new campaign with a workspace at creation time.
    """

    workspace_id: Optional[str] = None


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
