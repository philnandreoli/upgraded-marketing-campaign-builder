"""
Workspace member management routes.

Endpoints:
  GET    /api/workspaces/{id}/members            — List all workspace members
  POST   /api/workspaces/{id}/members            — Add a member
  PATCH  /api/workspaces/{id}/members/{user_id}  — Update member role
  DELETE /api/workspaces/{id}/members/{user_id}  — Remove a member
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.models.user import User
from backend.models.workspace import WorkspaceRole
from backend.infrastructure.auth import get_current_user

# Access get_campaign_store through the workspaces module so that test patches on
# backend.api.workspaces.get_campaign_store continue to work without modification.
import backend.api.workspaces as _ws

from backend.api.workspaces import (
    WorkspaceAction,
    _authorize_workspace,
)

router = APIRouter(tags=["workspaces"])


# ---------------------------------------------------------------------------
# Request / Response DTOs
# ---------------------------------------------------------------------------

class AddWorkspaceMemberRequest(BaseModel):
    user_id: str
    role: Literal["creator", "contributor", "viewer"] = "viewer"


class UpdateWorkspaceMemberRoleRequest(BaseModel):
    role: Literal["creator", "contributor", "viewer"]


class WorkspaceMemberResponse(BaseModel):
    workspace_id: str
    user_id: str
    role: str
    added_at: datetime
    display_name: Optional[str] = None
    email: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/workspaces/{workspace_id}/members", response_model=list[WorkspaceMemberResponse])
async def list_workspace_members(
    workspace_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> list[WorkspaceMemberResponse]:
    """List all members of a workspace. Requires workspace membership or admin."""
    store = _ws.get_campaign_store()
    workspace = await store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.READ, store)
    members = await store.list_workspace_members(workspace_id)
    return [
        WorkspaceMemberResponse(
            workspace_id=m.workspace_id,
            user_id=m.user_id,
            role=m.role.value,
            added_at=m.added_at,
            display_name=m.display_name,
            email=m.email,
        )
        for m in members
    ]


@router.post("/workspaces/{workspace_id}/members", status_code=201, response_model=WorkspaceMemberResponse)
async def add_workspace_member(
    workspace_id: str,
    body: AddWorkspaceMemberRequest,
    user: Optional[User] = Depends(get_current_user),
) -> WorkspaceMemberResponse:
    """Add a member to a workspace. Requires CREATOR role or admin."""
    store = _ws.get_campaign_store()
    workspace = await store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.MANAGE_MEMBERS, store)

    target_user = await store.get_user(body.user_id)
    if target_user is None or not target_user.is_active:
        raise HTTPException(status_code=404, detail="User not found or inactive")

    role = WorkspaceRole(body.role)
    await store.add_workspace_member(workspace_id, body.user_id, role)
    now = datetime.utcnow()

    return WorkspaceMemberResponse(
        workspace_id=workspace_id,
        user_id=body.user_id,
        role=body.role,
        added_at=now,
    )


@router.patch("/workspaces/{workspace_id}/members/{target_user_id}", response_model=WorkspaceMemberResponse)
async def update_workspace_member_role(
    workspace_id: str,
    target_user_id: str,
    body: UpdateWorkspaceMemberRoleRequest,
    user: Optional[User] = Depends(get_current_user),
) -> WorkspaceMemberResponse:
    """Update a member's role in a workspace. Requires CREATOR role or admin."""
    store = _ws.get_campaign_store()
    workspace = await store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.MANAGE_MEMBERS, store)

    existing_role = await store.get_workspace_member_role(workspace_id, target_user_id)
    if existing_role is None:
        raise HTTPException(status_code=404, detail="Member not found")

    role = WorkspaceRole(body.role)
    try:
        await store.update_workspace_member_role(workspace_id, target_user_id, role)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    members = await store.list_workspace_members(workspace_id)
    member = next((m for m in members if m.user_id == target_user_id), None)
    added_at = member.added_at if member else datetime.utcnow()

    return WorkspaceMemberResponse(
        workspace_id=workspace_id,
        user_id=target_user_id,
        role=body.role,
        added_at=added_at,
    )


@router.delete("/workspaces/{workspace_id}/members/{target_user_id}")
async def remove_workspace_member(
    workspace_id: str,
    target_user_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> Response:
    """Remove a member from a workspace. Requires CREATOR role or admin.
    Prevents removing the last CREATOR."""
    store = _ws.get_campaign_store()
    workspace = await store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.MANAGE_MEMBERS, store)

    members = await store.list_workspace_members(workspace_id)
    member = next((m for m in members if m.user_id == target_user_id), None)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    creator_count = sum(1 for m in members if m.role == WorkspaceRole.CREATOR)
    if member.role == WorkspaceRole.CREATOR and creator_count <= 1:
        raise HTTPException(status_code=409, detail="Cannot remove the last CREATOR")

    await store.remove_workspace_member(workspace_id, target_user_id)
    return Response(status_code=204)
