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
