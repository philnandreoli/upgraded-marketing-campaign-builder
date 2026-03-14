"""
Shared FastAPI dependencies for the API layer.

Provides RBAC authorization helpers used across campaign route modules:
  - Action            — enum of allowed campaign actions
  - _authorize        — enforce the RBAC matrix for a given action
  - get_campaign_for_read  — FastAPI dependency: load + authorize READ
  - get_campaign_for_write — FastAPI dependency: load + authorize WRITE
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from fastapi import Depends, HTTPException

from backend.models.campaign import Campaign
from backend.models.user import CampaignMemberRole, User
from backend.models.workspace import WorkspaceRole
from backend.infrastructure.auth import get_current_user
from backend.infrastructure.campaign_store import get_campaign_store


class Action(str, Enum):
    """Actions that can be performed on a campaign, used in authorization checks."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    MANAGE_MEMBERS = "manage_members"


async def _authorize(campaign_id: str, user: Optional[User], action: Action, store: Any) -> None:
    """Enforce RBAC for campaign access.

    Authorization matrix:
      Platform Role | Campaign Member  | Workspace Member | READ | WRITE | DELETE | MANAGE
      admin         | any/none         | any/none         |  ✅  |  ✅   |  ✅    |  ✅
      builder       | owner            | —                |  ✅  |  ✅   |  ✅    |  ✅
      builder       | editor           | —                |  ✅  |  ✅   |  ❌    |  ❌
      builder       | viewer           | —                |  ✅  |  ❌   |  ❌    |  ❌
      builder       | none             | ws CREATOR       |  ✅  |  ✅   |  ✅    |  ✅
      builder       | none             | ws CONTRIBUTOR   |  ✅  |  ✅   |  ❌    |  ❌
      builder       | none             | ws VIEWER        |  ✅  |  ❌   |  ❌    |  ❌
      builder       | none             | none             |  ❌  |  ❌   |  ❌    |  ❌ (404)
      viewer        | any member       | —                |  ✅  |  ❌   |  ❌    |  ❌
      viewer        | none             | ws any           |  ✅  |  ❌   |  ❌    |  ❌

    When auth is disabled (user is None) all campaigns are accessible.
    Raises 404 when the user has no membership (to avoid leaking campaign existence).
    Raises 403 when authenticated but the action exceeds the user's permission.

    Note: Platform VIEWER role never gets write access regardless of workspace role.
    """
    if user is None:
        return  # auth disabled — allow everything

    if user.is_admin:
        return  # admins have full access  # Step 1: admin → full access

    member_role = await store.get_member_role(campaign_id, user.id)

    allowed: bool
    if member_role is not None:
        # Step 2: Direct campaign membership — use campaign role
        if user.can_build:
            if member_role == CampaignMemberRole.OWNER:
                allowed = True
            elif member_role == CampaignMemberRole.EDITOR:
                allowed = action in (Action.READ, Action.WRITE)
            else:  # CampaignMemberRole.VIEWER
                allowed = action == Action.READ
        else:  # pure viewer platform role
            allowed = action == Action.READ
    else:
        # No direct campaign membership — check workspace fallback
        campaign = await store.get(campaign_id)
        if campaign is not None and campaign.workspace_id is not None:
            ws_role = await store.get_workspace_member_role(campaign.workspace_id, user.id)
            if ws_role is not None:
                # Step 3: Derive permissions from workspace role
                # Platform VIEWER is always capped at READ regardless of workspace role
                if not user.can_build:
                    allowed = action == Action.READ
                elif ws_role == WorkspaceRole.CREATOR:
                    allowed = True
                elif ws_role == WorkspaceRole.CONTRIBUTOR:
                    allowed = action in (Action.READ, Action.WRITE)
                else:  # WorkspaceRole.VIEWER
                    allowed = action == Action.READ
                if not allowed:
                    raise HTTPException(status_code=403, detail="Insufficient permissions")
                return
        # Step 4: Owner_id fallback (backward compat for orphaned campaigns)
        if campaign is not None and campaign.owner_id == user.id:
            return  # full access for owner
        # Step 5: No membership at all — 404 to avoid leaking campaign existence
        raise HTTPException(status_code=404, detail="Campaign not found")

    if not allowed:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


async def get_campaign_for_read(
    workspace_id: str,
    campaign_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> Campaign:
    """FastAPI dependency: load a campaign and authorize READ access."""
    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None or campaign.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await _authorize(campaign_id, user, Action.READ, store)
    return campaign


async def get_campaign_for_write(
    workspace_id: str,
    campaign_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> Campaign:
    """FastAPI dependency: load a campaign and authorize WRITE access."""
    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None or campaign.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await _authorize(campaign_id, user, Action.WRITE, store)
    return campaign
