"""
Workspace REST API — CRUD routes.

Endpoints:
  POST   /api/workspaces                        — Create a workspace
  GET    /api/workspaces                        — List workspaces the user belongs to
  GET    /api/workspaces/{id}                   — Get workspace details
  PATCH  /api/workspaces/{id}                   — Update workspace name/description
  DELETE /api/workspaces/{id}                   — Delete workspace (orphans campaigns)
  GET    /api/workspaces/{id}/campaigns         — List campaigns in workspace

Membership routes live in workspace_members.py.
Shared RBAC helpers (_authorize_workspace, WorkspaceAction) and Pydantic DTOs are
defined here and imported by workspace_members.py.
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
from backend.services.auth import get_current_user
from backend.services.campaign_store import get_campaign_store

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

    result: list[WorkspaceSummary] = []
    for ws in workspaces:
        if user is not None:
            role = await store.get_workspace_member_role(ws.id, user.id)
            role_str = role.value if role is not None else WorkspaceRole.VIEWER.value
        else:
            role_str = WorkspaceRole.CREATOR.value

        result.append(
            WorkspaceSummary(
                id=ws.id,
                name=ws.name,
                is_personal=ws.is_personal,
                role=role_str,
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


@router.get("/workspaces/{workspace_id}/campaigns")
async def list_workspace_campaigns(
    workspace_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> list[dict]:
    """List campaigns in a workspace. Requires workspace membership or admin."""
    store = get_campaign_store()
    workspace = await store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.READ, store)
    campaigns = await store.list_workspace_campaigns(workspace_id)
    return [c.model_dump(mode="json") for c in campaigns]


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
