"""
Workspace REST API — CRUD routes.

Endpoints:
  POST   /api/workspaces                        — Create a workspace
  GET    /api/workspaces                        — List workspaces the user belongs to
  GET    /api/workspaces/{id}                   — Get workspace details
  PATCH  /api/workspaces/{id}                   — Update workspace name/description
  DELETE /api/workspaces/{id}                   — Delete workspace

Membership routes live in workspace_members.py.
Campaign routes live in campaigns.py (mounted under /api/workspaces/{id}).
Shared RBAC helpers (_authorize_workspace, WorkspaceAction) and Pydantic DTOs are
defined here and imported by workspace_members.py and campaigns.py.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.models.user import User, UserRole
from backend.models.workspace import Workspace, WorkspaceRole
from backend.infrastructure.auth import get_current_user
from backend.infrastructure.campaign_store import get_campaign_store

router = APIRouter(tags=["workspaces"])


# ---------------------------------------------------------------------------
# Authorization helpers
# ---------------------------------------------------------------------------

class WorkspaceAction(str, Enum):
    """Actions that can be performed on a workspace, used in authorization checks."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    MANAGE_MEMBERS = "manage_members"


async def _authorize_workspace(
    workspace_id: str,
    user: Optional[User],
    action: WorkspaceAction,
    store: Any,
) -> None:
    """Enforce RBAC for workspace access.

    Authorization matrix:
      Platform Role | Workspace Role | READ | WRITE | DELETE | MANAGE_MEMBERS
      admin         | (any/none)     |  ✅  |  ✅   |  ✅    |  ✅
      any           | CREATOR        |  ✅  |  ✅   |  ✅    |  ✅
      any           | CONTRIBUTOR    |  ✅  |  ❌   |  ❌    |  ❌
      any           | VIEWER         |  ✅  |  ❌   |  ❌    |  ❌
      any           | (none)         |  ❌  |  ❌   |  ❌    |  ❌

    When auth is disabled (user is None) all workspaces are accessible.
    Raises 404 when the user has no membership (to avoid leaking workspace existence).
    Raises 403 when authenticated but the action exceeds the user's permission.
    """
    if user is None:
        return  # auth disabled — allow everything

    if user.is_admin:
        return  # admins have full access

    role = await store.get_workspace_member_role(workspace_id, user.id)
    if role is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if role == WorkspaceRole.CREATOR:
        allowed = True
    else:
        # CONTRIBUTOR and VIEWER get READ-only workspace access
        allowed = action == WorkspaceAction.READ

    if not allowed:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


# ---------------------------------------------------------------------------
# Request / Response DTOs
# ---------------------------------------------------------------------------

class CreateWorkspaceRequest(BaseModel):
    name: str
    description: Optional[str] = None


class UpdateWorkspaceRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    owner_id: str
    is_personal: bool
    created_at: datetime
    updated_at: datetime


class WorkspaceSummary(BaseModel):
    id: str
    name: str
    is_personal: bool
    role: str  # the current user's role in this workspace
    member_count: int = 0
    campaign_count: int = 0
    owner_id: Optional[str] = None
    owner_display_name: Optional[str] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/workspaces", status_code=201, response_model=WorkspaceResponse)
async def create_workspace(
    body: CreateWorkspaceRequest,
    user: Optional[User] = Depends(get_current_user),
) -> WorkspaceResponse:
    """Create a workspace. Requires campaign_builder or admin role.
    The creator is automatically added as a CREATOR member."""
    if user is not None and user.is_viewer and not user.is_admin:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    store = get_campaign_store()
    owner_id = user.id if user is not None else "local"
    workspace = await store.create_workspace(
        name=body.name,
        owner_id=owner_id,
        description=body.description,
    )
    return _workspace_to_response(workspace)


@router.get("/workspaces", response_model=list[WorkspaceSummary])
async def list_workspaces(
    user: Optional[User] = Depends(get_current_user),
) -> list[WorkspaceSummary]:
    """List workspaces the current user belongs to. Admins see all workspaces."""
    store = get_campaign_store()
    if user is not None:
        workspaces = await store.list_workspaces(user.id, is_admin=user.is_admin)
    else:
        workspaces = await store.list_workspaces("local", is_admin=True)

    summary_map: dict[str, dict[str, Any]] = {}
    workspace_ids = [ws.id for ws in workspaces]
    if hasattr(store, "get_workspace_summaries"):
        summary_map = await store.get_workspace_summaries(
            workspace_ids,
            user_id=user.id if user is not None else None,
            is_admin=user.is_admin if user is not None else True,
        )

    result: list[WorkspaceSummary] = []
    for ws in workspaces:
        summary = summary_map.get(ws.id)
        if summary is not None:
            role_str = str(summary.get("role", WorkspaceRole.VIEWER.value))
            member_count = int(summary.get("member_count", 0))
            campaign_count = int(summary.get("campaign_count", 0))
            owner_display_name = summary.get("owner_display_name")
        else:
            if user is not None:
                role = await store.get_workspace_member_role(ws.id, user.id)
                role_str = role.value if role is not None else WorkspaceRole.VIEWER.value
            else:
                role_str = WorkspaceRole.CREATOR.value
            members = await store.list_workspace_members(ws.id)
            campaigns = await store.list_workspace_campaigns(ws.id)
            member_count = len(members)
            campaign_count = len(campaigns)
            if ws.owner_id:
                owner_user = await store.get_user(ws.owner_id)
                owner_display_name = (
                    owner_user.display_name if owner_user is not None else None
                )
            else:
                owner_display_name = None

        result.append(
            WorkspaceSummary(
                id=ws.id,
                name=ws.name,
                is_personal=ws.is_personal,
                role=role_str,
                member_count=member_count,
                campaign_count=campaign_count,
                owner_id=ws.owner_id,
                owner_display_name=owner_display_name,
                created_at=ws.created_at,
            )
        )
    return result


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> WorkspaceResponse:
    """Get workspace details. Requires workspace membership or admin."""
    store = get_campaign_store()
    workspace = await store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.READ, store)
    return _workspace_to_response(workspace)


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    body: UpdateWorkspaceRequest,
    user: Optional[User] = Depends(get_current_user),
) -> WorkspaceResponse:
    """Update workspace name or description. Requires CREATOR role or admin."""
    store = get_campaign_store()
    workspace = await store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.WRITE, store)
    try:
        updated = await store.update_workspace(
            workspace_id,
            name=body.name,
            description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _workspace_to_response(updated)


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> Response:
    """Delete a workspace. Personal workspaces cannot be deleted.
    Campaigns belonging to the workspace are orphaned (not deleted)."""
    store = get_campaign_store()
    workspace = await store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.DELETE, store)
    if workspace.is_personal:
        raise HTTPException(status_code=409, detail="Personal workspaces cannot be deleted")
    await store.delete_workspace(workspace_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _workspace_to_response(workspace: Workspace) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        description=workspace.description,
        owner_id=workspace.owner_id,
        is_personal=workspace.is_personal,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )
