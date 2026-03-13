"""
Campaign REST API — CRUD and user-profile routes.

Endpoints:
  GET    /api/me                  — Return the current user's profile and role flags
  POST   /api/campaigns           — Create a campaign from a brief and start the pipeline
  GET    /api/campaigns           — List all campaigns
  GET    /api/campaigns/{id}      — Get a single campaign
  DELETE /api/campaigns/{id}      — Delete a campaign
  GET    /api/campaigns/{id}/events — Get persisted event log for a campaign

Workflow command routes live in campaign_workflow.py.
Member management routes live in campaign_members.py.
Shared RBAC helpers live in backend.apps.api.dependencies.
Shared DTOs live in backend.apps.api.schemas.campaigns and
backend.apps.api.schemas.workflow.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from backend.models.campaign import Campaign, CampaignBrief
from backend.models.user import User, UserRole
from backend.models.workspace import WorkspaceRole
from backend.models.events import CampaignEventLog
from backend.infrastructure.auth import get_current_user
from backend.infrastructure.campaign_store import get_campaign_store
from backend.infrastructure.event_store import get_event_store
from backend.application.campaign_workflow_service import get_workflow_service
from backend.infrastructure.workflow_executor import get_executor, WorkflowJob
import asyncio

from backend.apps.api.dependencies import Action, _authorize, get_campaign_for_read, get_campaign_for_write  # noqa: F401
from backend.apps.api.schemas.campaigns import (  # noqa: F401
    AddMemberRequest,
    AssignWorkspaceRequest,
    CampaignMemberResponse,
    CampaignSummary,
    CreateCampaignRequest,
    CreateCampaignResponse,
    MeResponse,
    UpdateMemberRoleRequest,
)
from backend.apps.api.schemas.workflow import (  # noqa: F401
    PieceDecisionRequest,
    PieceDecisionResponse,
    PieceNotesResponse,
    UpdatePieceNotesRequest,
    WorkflowActionResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["campaigns"])


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
        results = await asyncio.gather(
            *[store.get_workspace(ws_id) for ws_id in unique_ws_ids],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Failed to look up workspace name: %s", result)
            elif result is not None:
                ws_names[result.id] = result.name

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
    data = campaign.model_dump(mode="json")
    # Enrich with workspace object so the frontend can display name/badge
    if campaign.workspace_id:
        store = get_campaign_store()
        ws = await store.get_workspace(campaign.workspace_id)
        if ws:
            data["workspace"] = {"id": ws.id, "name": ws.name, "is_personal": ws.is_personal}
    return data


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
    data = campaign.model_dump(mode="json")
    # Enrich with workspace object so the frontend can display name/badge
    if campaign.workspace_id:
        ws = await store.get_workspace(campaign.workspace_id)
        if ws:
            data["workspace"] = {"id": ws.id, "name": ws.name, "is_personal": ws.is_personal}
    return data


@router.get("/campaigns/{campaign_id}/events", response_model=list[CampaignEventLog])
async def get_campaign_events(
    campaign: Campaign = Depends(get_campaign_for_read),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[CampaignEventLog]:
    """Return persisted pipeline event logs for a campaign.

    Events are ordered chronologically (oldest first).  Use ``limit`` and
    ``offset`` to paginate through large histories.
    """
    store = get_event_store()
    return await store.get_events(campaign.id, limit=limit, offset=offset)
