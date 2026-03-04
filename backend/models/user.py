"""
User data models — represent platform users and their roles.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRole(str, Enum):
    """Platform-level roles that control what a user is allowed to do."""

    ADMIN = "admin"
    CAMPAIGN_BUILDER = "campaign_builder"
    VIEWER = "viewer"


class CampaignMemberRole(str, Enum):
    """Per-campaign roles that define a user's access within a specific campaign."""

    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------

class User(BaseModel):
    """A provisioned platform user, created JIT from OIDC claims."""

    id: str = Field(description="OIDC oid/sub — the unique identifier from the identity provider.")
    email: Optional[str] = Field(default=None, description="Email address from JWT claims.")
    display_name: Optional[str] = Field(default=None, description="Human-readable name from JWT claims.")
    role: UserRole = Field(default=UserRole.VIEWER, description="Platform role assigned to this user.")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True, description="Whether the user account is active.")


# ---------------------------------------------------------------------------
# Campaign membership model
# ---------------------------------------------------------------------------

class CampaignMember(BaseModel):
    """Associates a user with a campaign and defines their per-campaign role."""

    campaign_id: str = Field(description="ID of the campaign.")
    user_id: str = Field(description="ID of the user.")
    role: CampaignMemberRole = Field(description="Per-campaign role for this user.")
    added_at: datetime = Field(default_factory=datetime.utcnow, description="When the membership was created.")
