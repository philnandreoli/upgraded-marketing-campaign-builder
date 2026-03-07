"""
User data models — represent platform users and their roles.

A user may hold multiple platform roles simultaneously.  The only
constraint is that ``campaign_builder`` and ``viewer`` are mutually
exclusive (a user cannot hold both at the same time).  ``admin`` can
be combined freely with either ``campaign_builder`` or ``viewer``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from backend.models.workspace import WorkspaceRole, WorkspaceMember  # noqa: F401 — re-exported for convenience


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
# Helpers
# ---------------------------------------------------------------------------

def roles_from_db(value: str) -> List[UserRole]:
    """Parse a comma-separated DB string into a list of ``UserRole`` enums."""
    return [UserRole(v.strip()) for v in value.split(",") if v.strip()]


def roles_to_db(roles: List[UserRole]) -> str:
    """Serialize a list of ``UserRole`` enums to a comma-separated DB string."""
    return ",".join(sorted(r.value for r in roles))


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------

class User(BaseModel):
    """A provisioned platform user, created JIT from OIDC claims."""

    id: str = Field(description="OIDC oid/sub — the unique identifier from the identity provider.")
    email: Optional[str] = Field(default=None, description="Email address from JWT claims.")
    display_name: Optional[str] = Field(default=None, description="Human-readable name from JWT claims.")
    roles: List[UserRole] = Field(default_factory=lambda: [UserRole.VIEWER], description="Platform roles assigned to this user.")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True, description="Whether the user account is active.")

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v: List[UserRole]) -> List[UserRole]:
        if not v:
            raise ValueError("A user must have at least one role.")
        if UserRole.CAMPAIGN_BUILDER in v and UserRole.VIEWER in v:
            raise ValueError("A user cannot be both a campaign_builder and a viewer.")
        return sorted(set(v), key=lambda r: r.value)

    # ----- convenience helpers -----

    @property
    def is_admin(self) -> bool:
        return UserRole.ADMIN in self.roles

    @property
    def can_build(self) -> bool:
        """True unless the user is purely a viewer (no builder/admin role)."""
        return UserRole.VIEWER not in self.roles

    @property
    def is_viewer(self) -> bool:
        return UserRole.VIEWER in self.roles and UserRole.ADMIN not in self.roles


# ---------------------------------------------------------------------------
# Campaign membership model
# ---------------------------------------------------------------------------

class CampaignMember(BaseModel):
    """Associates a user with a campaign and defines their per-campaign role."""

    campaign_id: str = Field(description="ID of the campaign.")
    user_id: str = Field(description="ID of the user.")
    role: CampaignMemberRole = Field(description="Per-campaign role for this user.")
    added_at: datetime = Field(default_factory=datetime.utcnow, description="When the membership was created.")
