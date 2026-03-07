"""
Campaign REST API — CRUD and user-profile routes.

Endpoints:
  GET    /api/me                  — Return the current user's profile and role flags
  POST   /api/campaigns           — Create a campaign from a brief and start the pipeline
  GET    /api/campaigns           — List all campaigns
  GET    /api/campaigns/{id}      — Get a single campaign
  DELETE /api/campaigns/{id}      — Delete a campaign

Workflow command routes live in campaign_workflow.py.
Member management routes live in campaign_members.py.
Shared RBAC helpers (Action, _authorize, get_campaign_for_read/write) and Pydantic
DTOs are defined here and imported by the other two routers.
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.models.campaign import Campaign, CampaignBrief
from backend.models.user import CampaignMemberRole, User, UserRole
from backend.models.workspace import WorkspaceRole
from backend.services.auth import get_current_user
from backend.services.campaign_store import get_campaign_store
from backend.services.campaign_workflow_service import get_workflow_service
from backend.services.workflow_executor import get_executor, WorkflowJob
import asyncio

logger = logging.getLogger(__name__)
router = APIRouter(tags=["campaigns"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    campaign_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> Campaign:
    """FastAPI dependency: load a campaign and authorize READ access."""
    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await _authorize(campaign_id, user, Action.READ, store)
    return campaign


async def get_campaign_for_write(
    campaign_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> Campaign:
    """FastAPI dependency: load a campaign and authorize WRITE access."""
    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await _authorize(campaign_id, user, Action.WRITE, store)
    return campaign


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


class WorkflowActionResponse(BaseModel):
    campaign_id: str
    message: str


class PieceDecisionResponse(BaseModel):
    campaign_id: str
    piece_index: int
    approval_status: str
    message: str


class PieceNotesResponse(BaseModel):
    campaign_id: str
    piece_index: int
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


# ---------------------------------------------------------------------------
# Workflow request models (defined here; imported by campaign_workflow.py)
# ---------------------------------------------------------------------------

class PieceDecisionRequest(BaseModel):
    approved: bool
    edited_content: Optional[str] = None
    notes: str = ""


class UpdatePieceNotesRequest(BaseModel):
    notes: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/me", response_model=MeResponse)
async def get_me(
    user: Optional[User] = Depends(get_current_user),
) -> MeResponse:
    """Return the current user's profile and role flags (lightweight, no DB joins)."""
    if user is None:
        # Auth disabled — return a default builder profile for local development.
        return MeResponse(
            id="local",
            email=None,
            display_name="Local Dev",
            roles=[UserRole.CAMPAIGN_BUILDER.value],
            is_admin=False,
            can_build=True,
            is_viewer=False,
        )
    return MeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        roles=[r.value for r in user.roles],
        is_admin=user.is_admin,
        can_build=user.can_build,
        is_viewer=user.is_viewer,
    )


@router.post("/campaigns", status_code=201, response_model=CreateCampaignResponse)
async def create_campaign(
    request: CreateCampaignRequest,
    user: Optional[User] = Depends(get_current_user),
) -> CreateCampaignResponse:
    """Create a new campaign and kick off the agent pipeline in the background.

    If ``workspace_id`` is provided in the request body the campaign is
    associated with that workspace.  Only workspace CREATORs (or ADMINs) may
    create campaigns within a workspace.  When omitted, the campaign is
    created as an orphan (no workspace).
    """
    # When auth is enabled, only campaign_builder and admin may create campaigns.
    # When auth is disabled (user is None) all requests are allowed (dev mode).
    if user is not None and user.is_viewer:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    workspace_id = request.workspace_id
    if workspace_id is not None and user is not None and not user.is_admin:
        # Verify the user is a CREATOR member of the target workspace
        store = get_campaign_store()
        workspace = await store.get_workspace(workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        ws_role = await store.get_workspace_member_role(workspace_id, user.id)
        if ws_role != WorkspaceRole.CREATOR:
            raise HTTPException(status_code=403, detail="Only workspace CREATORs can create campaigns in a workspace")

    # Build a plain CampaignBrief from the request (workspace_id is handled separately)
    brief = CampaignBrief(**request.model_dump(exclude={"workspace_id"}))

    try:
        logger.info("Creating campaign for user %s with brief: %s", user.id if user else "anonymous", brief.model_dump())
        service = get_workflow_service()
        campaign = await service.create_campaign(brief, user, workspace_id=workspace_id)
        logger.info("Campaign %s created successfully", campaign.id)
    except Exception as exc:
        logger.exception("Failed to create campaign: %s", exc)
        raise HTTPException(status_code=500, detail=f"Campaign creation failed: {exc}")

    # Dispatch the pipeline to the configured executor (runs in background)
    await get_executor().dispatch(WorkflowJob(campaign_id=campaign.id, action="start_pipeline"))

    return CreateCampaignResponse(
        id=campaign.id,
        status=campaign.status.value,
        message="Campaign created. Pipeline is running — connect to WebSocket for live updates.",
    )


@router.get("/campaigns", response_model=list[CampaignSummary])
async def list_campaigns(
    user: Optional[User] = Depends(get_current_user),
) -> list[CampaignSummary]:
    """Return campaigns visible to the current user (summary view)."""
    store = get_campaign_store()
    if user is not None:
        campaigns = await store.list_accessible(user.id, is_admin=user.is_admin)
    else:
        campaigns = await store.list_all()

    # Resolve workspace names in a single batch (one lookup per unique workspace_id)
    unique_ws_ids = {c.workspace_id for c in campaigns if c.workspace_id is not None}
    ws_names: dict[str, Optional[str]] = {}
    if unique_ws_ids:
        workspaces = await asyncio.gather(
            *[store.get_workspace(ws_id) for ws_id in unique_ws_ids]
        )
        for ws in workspaces:
            if ws is not None:
                ws_names[ws.id] = ws.name

    return [
        CampaignSummary(
            id=c.id,
            status=c.status.value,
            product_or_service=c.brief.product_or_service,
            goal=c.brief.goal,
            owner_id=c.owner_id,
            workspace_id=c.workspace_id,
            workspace_name=ws_names.get(c.workspace_id) if c.workspace_id else None,
            created_at=c.created_at.isoformat(),
            updated_at=c.updated_at.isoformat(),
        )
        for c in campaigns
    ]


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign: Campaign = Depends(get_campaign_for_read),
) -> dict[str, Any]:
    """Return the full campaign document."""
    return campaign.model_dump(mode="json")


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> Response:
    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await _authorize(campaign_id, user, Action.DELETE, store)
    await store.delete(campaign_id)
    return Response(status_code=204)


@router.patch("/campaigns/{campaign_id}/workspace")
async def assign_campaign_workspace(
    campaign_id: str,
    body: AssignWorkspaceRequest,
    user: Optional[User] = Depends(get_current_user),
) -> dict[str, Any]:
    """Move or assign a campaign to a workspace.  Admin-only endpoint.

    Setting ``workspace_id`` to ``null`` orphans the campaign (no workspace).
    """
    if user is None or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Validate target workspace exists (if not orphaning)
    if body.workspace_id is not None:
        workspace = await store.get_workspace(body.workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")

    campaign = await store.move_campaign(campaign_id, body.workspace_id)
    return campaign.model_dump(mode="json")
