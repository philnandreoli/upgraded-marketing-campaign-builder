"""
Campaign REST API routes.

Endpoints:
  GET    /api/me                       — Return the current user's profile and role flags
  POST   /api/campaigns               — Create a campaign from a brief and start the pipeline
  GET    /api/campaigns                — List all campaigns
  GET    /api/campaigns/{id}           — Get a single campaign
  DELETE /api/campaigns/{id}           — Delete a campaign
  POST   /api/campaigns/{id}/clarify   — Submit answers to strategy clarification questions
  PATCH  /api/campaigns/{id}/content/{piece_index}/decision — Immediately persist a per-piece approval/rejection
  POST   /api/campaigns/{id}/content-approve — Submit per-piece content approval decisions (finalize)
  PATCH  /api/campaigns/{id}/content/{piece_index}/notes — Update human_notes on an approved piece
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.agents.coordinator_agent import CoordinatorAgent
from backend.models.campaign import Campaign, CampaignBrief
from backend.models.messages import ClarificationResponse, ContentApprovalResponse, HumanReviewResponse
from backend.models.user import CampaignMemberRole, User, UserRole, roles_to_db
from backend.services.auth import get_current_user
from backend.services.campaign_store import get_campaign_store
from backend.services.campaign_workflow_service import CampaignWorkflowService, WorkflowConflictError, get_workflow_service
from backend.api.websocket import manager as ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["campaigns"])

# ---------------------------------------------------------------------------
# Shared coordinator instance (reused across requests so the pending-review
# future map survives between the POST that launches the pipeline and the
# POST that submits the human review).
# ---------------------------------------------------------------------------
_coordinator: CoordinatorAgent | None = None


def _get_coordinator() -> CoordinatorAgent:
    global _coordinator
    if _coordinator is None:
        async def _broadcast(event: str, data: dict[str, Any]) -> None:
            await ws_manager.broadcast({"event": event, **data})

        _coordinator = CoordinatorAgent(on_event=_broadcast)
    return _coordinator


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
      Platform Role     | Campaign Membership | READ | WRITE | DELETE | MANAGE_MEMBERS
      admin             | (any/none)          |  ✅  |  ✅   |  ✅    |  ✅
      campaign_builder  | owner               |  ✅  |  ✅   |  ✅    |  ✅
      campaign_builder  | editor              |  ✅  |  ✅   |  ❌    |  ❌
      campaign_builder  | viewer              |  ✅  |  ❌   |  ❌    |  ❌
      campaign_builder  | (none)              |  ❌  |  ❌   |  ❌    |  ❌
      viewer            | owner/editor/viewer |  ✅  |  ❌   |  ❌    |  ❌
      viewer            | (none)              |  ❌  |  ❌   |  ❌    |  ❌

    When auth is disabled (user is None) all campaigns are accessible.
    Raises 404 when the user has no membership (to avoid leaking campaign existence).
    Raises 403 when authenticated but the action exceeds the user's permission.
    """
    if user is None:
        return  # auth disabled — allow everything

    if user.is_admin:
        return  # admins have full access

    member_role = await store.get_member_role(campaign_id, user.id)
    if member_role is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    allowed: bool
    if user.can_build:
        if member_role == CampaignMemberRole.OWNER:
            allowed = True
        elif member_role == CampaignMemberRole.EDITOR:
            allowed = action in (Action.READ, Action.WRITE)
        else:  # CampaignMemberRole.VIEWER
            allowed = action == Action.READ
    else:  # pure viewer role
        allowed = action == Action.READ

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
    created_at: str
    updated_at: str


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
    brief: CampaignBrief,
    background_tasks: BackgroundTasks,
    user: Optional[User] = Depends(get_current_user),
) -> CreateCampaignResponse:
    """Create a new campaign and kick off the agent pipeline in the background."""
    # When auth is enabled, only campaign_builder and admin may create campaigns.
    # When auth is disabled (user is None) all requests are allowed (dev mode).
    if user is not None and user.is_viewer:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        logger.info("Creating campaign for user %s with brief: %s", user.id if user else "anonymous", brief.model_dump())
        coordinator = _get_coordinator()
        service = get_workflow_service(coordinator)
        campaign = await service.create_campaign(brief, user)
        logger.info("Campaign %s created successfully", campaign.id)
    except Exception as exc:
        logger.exception("Failed to create campaign: %s", exc)
        raise HTTPException(status_code=500, detail=f"Campaign creation failed: {exc}")

    # Run the pipeline in the background so the HTTP response returns immediately
    background_tasks.add_task(_run_pipeline, coordinator, campaign)

    return CreateCampaignResponse(
        id=campaign.id,
        status=campaign.status.value,
        message="Campaign created. Pipeline is running — connect to WebSocket for live updates.",
    )


async def _run_pipeline(coordinator: CoordinatorAgent, campaign: Campaign) -> None:
    """Wrapper executed as a background task."""
    try:
        logger.info("Starting pipeline for campaign %s", campaign.id)
        await coordinator.run_pipeline(campaign)
        logger.info("Pipeline completed for campaign %s", campaign.id)
    except Exception as exc:
        logger.exception("Pipeline crashed for campaign %s: %s", campaign.id, exc)


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
    return [
        CampaignSummary(
            id=c.id,
            status=c.status.value,
            product_or_service=c.brief.product_or_service,
            goal=c.brief.goal,
            owner_id=c.owner_id,
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


@router.post("/campaigns/{campaign_id}/clarify", response_model=WorkflowActionResponse)
async def submit_clarification(
    response: ClarificationResponse,
    campaign: Campaign = Depends(get_campaign_for_write),
) -> WorkflowActionResponse:
    """Submit answers to strategy clarification questions."""
    workflow = get_workflow_service(_get_coordinator())
    try:
        await workflow.submit_clarification(campaign.id, response)
    except WorkflowConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return WorkflowActionResponse(message="Clarification submitted", campaign_id=campaign.id)


@router.post("/campaigns/{campaign_id}/review-clarify")
async def submit_review_clarification(
    campaign_id: str, response: ClarificationResponse
) -> dict[str, str]:
    """Legacy endpoint — review clarification is no longer used."""
    raise HTTPException(status_code=410, detail="Review clarification is no longer supported. Use /content-approve instead.")


@router.post("/campaigns/{campaign_id}/review")
async def submit_review(campaign_id: str, response: HumanReviewResponse) -> dict[str, str]:
    """Legacy endpoint — whole-campaign review is no longer used."""
    raise HTTPException(status_code=410, detail="Whole-campaign review is no longer supported. Use /content-approve instead.")


@router.post("/campaigns/{campaign_id}/content-approve", response_model=WorkflowActionResponse)
async def submit_content_approval(
    response: ContentApprovalResponse,
    campaign: Campaign = Depends(get_campaign_for_write),
) -> WorkflowActionResponse:
    """Submit per-piece content approval decisions."""
    workflow = get_workflow_service(_get_coordinator())
    try:
        await workflow.submit_content_approval(campaign.id, response)
    except ValueError:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return WorkflowActionResponse(message="Content approval submitted", campaign_id=campaign.id)


class PieceDecisionRequest(BaseModel):
    approved: bool
    edited_content: Optional[str] = None
    notes: str = ""


@router.patch("/campaigns/{campaign_id}/content/{piece_index}/decision", response_model=PieceDecisionResponse)
async def update_piece_decision(
    piece_index: int,
    body: PieceDecisionRequest,
    campaign: Campaign = Depends(get_campaign_for_write),
) -> PieceDecisionResponse:
    """Immediately persist an approve/reject decision for a single content piece.

    Saves the decision to the store straight away so the status survives a page
    refresh without requiring the user to first click "Submit Decisions".  The
    campaign status remains ``content_approval`` until the full batch
    ``/content-approve`` call finalises everything with the coordinator.

    Returns 404 if the campaign or piece does not exist, 409 if the campaign is
    not in ``content_approval`` status, or if an attempt is made to reject an
    already-approved piece (approved content is immutable).
    """
    workflow = get_workflow_service(_get_coordinator())
    try:
        result = await workflow.update_piece_decision(
            campaign.id, piece_index, body.approved, body.edited_content, body.notes
        )
        return PieceDecisionResponse(
            campaign_id=result["campaign_id"],
            piece_index=result["piece_index"],
            approval_status=result["approval_status"].value,
            message=result["message"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except WorkflowConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


class UpdatePieceNotesRequest(BaseModel):
    notes: str


@router.patch("/campaigns/{campaign_id}/content/{piece_index}/notes", response_model=PieceNotesResponse)
async def update_piece_notes(
    piece_index: int,
    body: UpdatePieceNotesRequest,
    campaign: Campaign = Depends(get_campaign_for_write),
) -> PieceNotesResponse:
    """Update human_notes on an already-approved content piece.

    Approved content is immutable — only the reviewer notes field may be
    changed via this endpoint.  Returns 404 if the campaign or piece does not
    exist and 409 if the piece has not yet been approved.
    """
    workflow = get_workflow_service(_get_coordinator())
    try:
        result = await workflow.update_piece_notes(campaign.id, piece_index, body.notes)
        return PieceNotesResponse(
            campaign_id=result["campaign_id"],
            piece_index=result["piece_index"],
            message=result["message"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except WorkflowConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


# ---------------------------------------------------------------------------
# Member management routes
# ---------------------------------------------------------------------------

@router.get("/campaigns/{campaign_id}/members")
async def list_campaign_members(
    campaign: Campaign = Depends(get_campaign_for_read),
) -> list[CampaignMemberResponse]:
    """List all members of a campaign. Requires READ access."""
    store = get_campaign_store()
    members = await store.list_members(campaign.id)
    return [
        CampaignMemberResponse(
            campaign_id=m.campaign_id,
            user_id=m.user_id,
            role=m.role.value,
            added_at=m.added_at,
        )
        for m in members
    ]


@router.post("/campaigns/{campaign_id}/members", status_code=201)
async def add_campaign_member(
    campaign_id: str,
    body: AddMemberRequest,
    user: Optional[User] = Depends(get_current_user),
) -> CampaignMemberResponse:
    """Add a member to a campaign. Requires MANAGE_MEMBERS access (owner or admin)."""
    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await _authorize(campaign_id, user, Action.MANAGE_MEMBERS, store)

    target_user = await store.get_user(body.user_id)
    if target_user is None or not target_user.is_active:
        raise HTTPException(status_code=404, detail="User not found or inactive")

    role = CampaignMemberRole(body.role)
    await store.add_member(campaign_id, body.user_id, role)

    await ws_manager.broadcast({
        "event": "member_added",
        "campaign_id": campaign_id,
        "user_id": body.user_id,
        "role": body.role,
    })

    return CampaignMemberResponse(
        campaign_id=campaign_id,
        user_id=body.user_id,
        role=body.role,
        added_at=datetime.utcnow(),
    )


@router.patch("/campaigns/{campaign_id}/members/{target_user_id}")
async def update_campaign_member_role(
    campaign_id: str,
    target_user_id: str,
    body: UpdateMemberRoleRequest,
    user: Optional[User] = Depends(get_current_user),
) -> CampaignMemberResponse:
    """Change a member's campaign role. Requires MANAGE_MEMBERS access."""
    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await _authorize(campaign_id, user, Action.MANAGE_MEMBERS, store)

    target_user = await store.get_user(target_user_id)
    if target_user is None or not target_user.is_active:
        raise HTTPException(status_code=404, detail="User not found or inactive")

    existing_member = await store.get_member(campaign_id, target_user_id)
    if existing_member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    role = CampaignMemberRole(body.role)
    await store.add_member(campaign_id, target_user_id, role)

    return CampaignMemberResponse(
        campaign_id=campaign_id,
        user_id=target_user_id,
        role=body.role,
        added_at=existing_member.added_at,
    )


@router.delete("/campaigns/{campaign_id}/members/{target_user_id}")
async def remove_campaign_member(
    campaign_id: str,
    target_user_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> Response:
    """Remove a member from a campaign. Requires MANAGE_MEMBERS access.
    Prevents removing the last owner."""
    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await _authorize(campaign_id, user, Action.MANAGE_MEMBERS, store)

    members = await store.list_members(campaign_id)
    member = next((m for m in members if m.user_id == target_user_id), None)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    owner_count = sum(1 for m in members if m.role == CampaignMemberRole.OWNER)
    if member.role == CampaignMemberRole.OWNER and owner_count <= 1:
        raise HTTPException(status_code=409, detail="Cannot remove the last owner")

    await store.remove_member(campaign_id, target_user_id)

    await ws_manager.broadcast({
        "event": "member_removed",
        "campaign_id": campaign_id,
        "user_id": target_user_id,
    })

    return Response(status_code=204)
