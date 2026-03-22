"""
Campaign REST API — CRUD and user-profile routes.

Endpoints:
  GET    /api/me                                           — Return the current user's profile and role flags
  POST   /api/workspaces/{workspace_id}/campaigns          — Create a draft campaign (does NOT start the pipeline)
  PATCH  /api/workspaces/{workspace_id}/campaigns/{id}     — Update a draft campaign's brief fields / wizard step
  GET    /api/workspaces/{workspace_id}/campaigns          — List campaigns in a workspace (drafts excluded by default)
  GET    /api/workspaces/{workspace_id}/campaigns/{id}     — Get a single campaign
  DELETE /api/workspaces/{workspace_id}/campaigns/{id}     — Delete a campaign
  GET    /api/workspaces/{workspace_id}/campaigns/{id}/events — Get persisted event log

Workflow command routes live in campaign_workflow.py (including /launch).
Member management routes live in campaign_members.py.
Shared RBAC helpers live in backend.apps.api.dependencies.
Shared DTOs live in backend.apps.api.schemas.campaigns and
backend.apps.api.schemas.workflow.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from backend.models.campaign import Campaign, CampaignBrief, CampaignStatus
from backend.models.user import User, UserRole
from backend.models.user_settings import UserSettingsPatch
from backend.models.workspace import WorkspaceRole
from backend.models.events import CampaignEventLog
from backend.infrastructure.auth import get_current_user
from backend.infrastructure.campaign_store import get_campaign_store
from backend.infrastructure.event_store import get_event_store
from backend.infrastructure.user_settings_store import get_user_settings_store
from backend.application.campaign_workflow_service import get_workflow_service
from backend.infrastructure.workflow_executor import get_executor, WorkflowJob

from backend.apps.api.dependencies import Action, _authorize, get_campaign_for_read, get_campaign_for_write  # noqa: F401
from backend.apps.api.schemas.campaigns import (  # noqa: F401
    AddMemberRequest,
    CampaignListResponse,
    CampaignMemberResponse,
    PaginationMeta,
    CampaignSummary,
    CreateCampaignRequest,
    CreateCampaignResponse,
    MeResponse,
    MeSettingsResponse,
    PatchMeSettingsRequest,
    UpdateDraftRequest,
    UpdateMemberRoleRequest,
)
from backend.apps.api.schemas.workflow import (  # noqa: F401
    PieceDecisionRequest,
    PieceDecisionResponse,
    PieceNotesResponse,
    UpdatePieceNotesRequest,
    WorkflowActionResponse,
)
from backend.core.exceptions import ConcurrentUpdateError
from backend.core.rate_limit import limiter

logger = logging.getLogger(__name__)
me_router = APIRouter(tags=["users"])
router = APIRouter(tags=["campaigns"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@me_router.get("/me", response_model=MeResponse)
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


@me_router.get("/me/settings", response_model=MeSettingsResponse)
async def get_me_settings(
    user: Optional[User] = Depends(get_current_user),
) -> MeSettingsResponse:
    """Return the current user's effective settings (persisted or defaults)."""
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    settings = await get_user_settings_store().get(user.id)
    return MeSettingsResponse(
        theme=settings.ui_theme,
        locale=settings.locale,
        timezone=settings.timezone,
        default_workspace_id=settings.default_workspace_id,
        notification_prefs=settings.notification_prefs,
        dashboard_prefs=settings.dashboard_prefs,
    )


@me_router.patch("/me/settings", response_model=MeSettingsResponse)
async def patch_me_settings(
    body: PatchMeSettingsRequest = Body(),
    user: Optional[User] = Depends(get_current_user),
) -> MeSettingsResponse:
    """Apply partial updates to current user's settings with strict validation."""
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    patch_data = body.model_dump(exclude_unset=True)
    workspace_id = patch_data.get("default_workspace_id")
    if workspace_id is not None:
        store = get_campaign_store()
        workspace = await store.get_workspace(workspace_id)
        if workspace is None:
            raise HTTPException(
                status_code=404,
                detail="Workspace not found",
            )
        membership = await store.get_workspace_member_role(workspace_id, user.id)
        if membership is None and not user.is_admin:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to set this workspace as default",
            )

    patch_kwargs: dict[str, Any] = {}
    if "theme" in patch_data:
        patch_kwargs["ui_theme"] = patch_data["theme"]
    if "locale" in patch_data:
        patch_kwargs["locale"] = patch_data["locale"]
    if "timezone" in patch_data:
        patch_kwargs["timezone"] = patch_data["timezone"]
    if "default_workspace_id" in patch_data:
        patch_kwargs["default_workspace_id"] = patch_data["default_workspace_id"]
    if "notification_prefs" in patch_data:
        patch_kwargs["notification_prefs"] = patch_data["notification_prefs"]
    if "dashboard_prefs" in patch_data:
        patch_kwargs["dashboard_prefs"] = patch_data["dashboard_prefs"]

    updated = await get_user_settings_store().patch(
        user.id,
        UserSettingsPatch(**patch_kwargs),
    )
    return MeSettingsResponse(
        theme=updated.ui_theme,
        locale=updated.locale,
        timezone=updated.timezone,
        default_workspace_id=updated.default_workspace_id,
        notification_prefs=updated.notification_prefs,
        dashboard_prefs=updated.dashboard_prefs,
    )


@router.post("/campaigns", status_code=201, response_model=CreateCampaignResponse)
@limiter.limit("10/minute")
async def create_campaign(
    workspace_id: str,
    request: Request,
    response: Response,
    body: CreateCampaignRequest = Body(),
    user: Optional[User] = Depends(get_current_user),
) -> CreateCampaignResponse:
    """Create a new draft campaign without dispatching the agent pipeline.

    The campaign is saved with ``status: draft``.  Call
    ``POST /campaigns/{id}/launch`` to start the agent pipeline once all
    wizard steps are complete.

    The campaign is associated with the workspace specified in the URL path.
    Only workspace CREATORs (or ADMINs) may create campaigns within a workspace.
    """
    # When auth is enabled, only campaign_builder and admin may create campaigns.
    # When auth is disabled (user is None) all requests are allowed (dev mode).
    if user is not None and user.is_viewer:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    store = get_campaign_store()
    workspace = await store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if user is not None and not user.is_admin:
        # Verify the user is a CREATOR member of the target workspace
        ws_role = await store.get_workspace_member_role(workspace_id, user.id)
        if ws_role != WorkspaceRole.CREATOR:
            raise HTTPException(status_code=403, detail="Only workspace CREATORs can create campaigns in a workspace")

    # Build a plain CampaignBrief from the request body
    brief = CampaignBrief(**body.model_dump())

    try:
        logger.info("Creating draft campaign for user %s with brief: %s", user.id if user else "anonymous", brief.model_dump())
        service = get_workflow_service()
        campaign = await service.create_campaign(brief, user, workspace_id=workspace_id)
        logger.info("Draft campaign %s created successfully", campaign.id)
    except Exception as exc:
        logger.exception("Failed to create campaign: %s", exc)
        raise HTTPException(status_code=500, detail="Campaign creation failed. Please try again or contact support.")

    return CreateCampaignResponse(
        id=campaign.id,
        status=campaign.status.value,
        message="Draft campaign created. Complete the wizard and call /launch to start the pipeline.",
    )


@router.patch("/campaigns/{campaign_id}", response_model=CreateCampaignResponse)
async def update_draft_campaign(
    workspace_id: str,
    campaign_id: str,
    body: UpdateDraftRequest = Body(),
    user: Optional[User] = Depends(get_current_user),
) -> CreateCampaignResponse:
    """Update brief fields and/or wizard step on a DRAFT campaign.

    Only campaigns with ``status: draft`` may be updated via this endpoint.
    Use ``POST /campaigns/{id}/launch`` to transition to the active pipeline.
    """
    if user is not None and user.is_viewer:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None or campaign.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status != CampaignStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Only draft campaigns can be updated via this endpoint")

    # RBAC: only owner, workspace CREATOR or admin may update
    await _authorize(campaign_id, user, Action.WRITE, store)

    # Apply partial updates to the brief
    brief_data = campaign.brief.model_dump()
    update_fields = body.model_dump(exclude_none=True, exclude={"wizard_step"})
    brief_data.update(update_fields)
    try:
        campaign.brief = CampaignBrief(**brief_data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Update wizard step if provided
    if body.wizard_step is not None:
        campaign.wizard_step = body.wizard_step

    campaign.updated_at = datetime.utcnow()

    try:
        campaign = await store.update(campaign)
    except ConcurrentUpdateError:
        raise HTTPException(
            status_code=409,
            detail="Draft was updated by another editor. Refetch the latest draft and retry your changes.",
        )
    except Exception as exc:
        logger.exception("Failed to update draft campaign %s: %s", campaign_id, exc)
        raise HTTPException(status_code=500, detail="Campaign update failed. Please try again or contact support.")

    return CreateCampaignResponse(
        id=campaign.id,
        status=campaign.status.value,
        message="Draft updated.",
    )


@router.get("/campaigns", response_model=CampaignListResponse)
async def list_campaigns(
    workspace_id: str,
    response: Response,
    user: Optional[User] = Depends(get_current_user),
    include_drafts: bool = Query(default=False, description="When true, include DRAFT campaigns in the response."),
    limit: int = Query(default=50, ge=1, le=200, description="Max number of campaigns to return (1–200)."),
    offset: int = Query(default=0, ge=0, description="Number of campaigns to skip before returning results."),
) -> CampaignListResponse:
    """Return paginated campaigns in the specified workspace visible to the current user.

    Draft campaigns are excluded by default.  Pass ``?include_drafts=true`` to
    include them (e.g. for the Drafts section of the dashboard).

    Returns a paginated envelope with ``items`` and ``pagination`` metadata.
    """
    store = get_campaign_store()
    workspace = await store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    from backend.api.workspaces import _authorize_workspace, WorkspaceAction
    await _authorize_workspace(workspace_id, user, WorkspaceAction.READ, store)
    campaigns, total_count = await store.list_workspace_campaigns(
        workspace_id, limit=limit, offset=offset, include_drafts=include_drafts,
    )

    returned_count = len(campaigns)
    has_more = offset + returned_count < total_count
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Offset"] = str(offset)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Returned-Count"] = str(returned_count)
    response.headers["X-Has-More"] = str(has_more).lower()

    items = [
        CampaignSummary(
            id=c.id,
            status=c.status.value,
            product_or_service=c.brief.product_or_service,
            goal=c.brief.goal,
            owner_id=c.owner_id,
            workspace_id=c.workspace_id,
            workspace_name=workspace.name,
            created_at=c.created_at,
            updated_at=c.updated_at,
            wizard_step=c.wizard_step,
        )
        for c in campaigns
    ]
    return CampaignListResponse(
        items=items,
        pagination=PaginationMeta(
            total_count=total_count,
            offset=offset,
            limit=limit,
            returned_count=returned_count,
            has_more=has_more,
        ),
    )


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    workspace_id: str,
    campaign: Campaign = Depends(get_campaign_for_read),
) -> dict[str, Any]:
    """Return the full campaign document."""
    if campaign.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    data = campaign.model_dump(mode="json")
    # Enrich with workspace object so the frontend can display name/badge
    store = get_campaign_store()
    ws = await store.get_workspace(campaign.workspace_id)
    if ws:
        data["workspace"] = {"id": ws.id, "name": ws.name, "is_personal": ws.is_personal}
    return data


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(
    workspace_id: str,
    campaign_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> Response:
    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None or campaign.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await _authorize(campaign_id, user, Action.DELETE, store)
    await store.delete(campaign_id)
    return Response(status_code=204)


@router.get("/campaigns/{campaign_id}/events", response_model=list[CampaignEventLog])
async def get_campaign_events(
    workspace_id: str,
    campaign: Campaign = Depends(get_campaign_for_read),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[CampaignEventLog]:
    """Return persisted pipeline event logs for a campaign.

    Events are ordered chronologically (oldest first).  Use ``limit`` and
    ``offset`` to paginate through large histories.
    """
    if campaign.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    store = get_event_store()
    return await store.get_events(campaign.id, limit=limit, offset=offset)
