"""
Workspace data models — represent workspaces, their members, and workspace-level roles.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class WorkspaceRole(str, Enum):
    """Per-workspace roles that define a member's access within a specific workspace."""

    CREATOR = "creator"      # Can create campaigns, edit, view, manage workspace members
    CONTRIBUTOR = "contributor"  # Can edit campaigns, view
    VIEWER = "viewer"        # Read-only access to campaigns in the workspace


# ---------------------------------------------------------------------------
# Workspace model
# ---------------------------------------------------------------------------

class Workspace(BaseModel):
    """A workspace that groups campaigns and members together."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique workspace identifier (UUID).")
    name: str = Field(description="Display name for the workspace.")
    description: Optional[str] = Field(default=None, description="Optional description of the workspace.")
    owner_id: str = Field(description="ID of the user who owns this workspace (FK to users.id).")
    is_personal: bool = Field(default=False, description="True for auto-created personal workspaces.")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Workspace name must not be empty.")
        return v


# ---------------------------------------------------------------------------
# WorkspaceMember model
# ---------------------------------------------------------------------------

class WorkspaceMember(BaseModel):
    """Associates a user with a workspace and defines their per-workspace role."""

    workspace_id: str = Field(description="ID of the workspace.")
    user_id: str = Field(description="ID of the user.")
    role: WorkspaceRole = Field(description="Per-workspace role for this user.")
    added_at: datetime = Field(default_factory=datetime.utcnow, description="When the membership was created.")
    display_name: Optional[str] = Field(default=None, description="Display name of the user.")
    email: Optional[str] = Field(default=None, description="Email address of the user.")
