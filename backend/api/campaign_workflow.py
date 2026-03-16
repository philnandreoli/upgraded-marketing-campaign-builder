"""
Campaign workflow command routes.

Endpoints:
  POST   /api/campaigns/{id}/launch           — Launch a draft campaign (triggers agent pipeline)
  POST   /api/campaigns/{id}/clarify          — Submit answers to strategy clarification questions
  POST   /api/campaigns/{id}/review-clarify   — Legacy endpoint (410 Gone)
  POST   /api/campaigns/{id}/review           — Legacy endpoint (410 Gone)
  POST   /api/campaigns/{id}/content-approve  — Submit per-piece content approval decisions
  PATCH  /api/campaigns/{id}/content/{piece_index}/decision — Persist a per-piece approval/rejection
  PATCH  /api/campaigns/{id}/content/{piece_index}/notes    — Update human_notes on an approved piece
  POST   /api/campaigns/{id}/resume           — Resume an interrupted pipeline
  POST   /api/campaigns/{id}/retry            — Retry the current failed stage
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)
from fastapi.responses import Response

from backend.models.campaign import Campaign, CampaignStatus
from backend.models.messages import ClarificationResponse, ContentApprovalResponse, HumanReviewResponse
from backend.models.user import User
from backend.infrastructure.auth import get_current_user
from backend.application.campaign_workflow_service import WorkflowConflictError, get_workflow_service
from backend.core.exceptions import ConcurrentUpdateError
from backend.infrastructure.workflow_executor import get_executor, WorkflowJob

from backend.apps.api.dependencies import get_campaign_for_write
from backend.apps.api.schemas.workflow import (
    PieceDecisionRequest,
    PieceDecisionResponse,
    PieceNotesResponse,
    UpdatePieceNotesRequest,
    WorkflowActionResponse,
)

router = APIRouter(tags=["campaigns"])


@router.post("/campaigns/{campaign_id}/launch", response_model=WorkflowActionResponse)
async def launch_campaign(
    campaign_id: str,
    campaign: Campaign = Depends(get_campaign_for_write),
) -> WorkflowActionResponse:
    """Launch a draft campaign by dispatching the agent pipeline.

    Transitions the campaign from ``draft`` to the active pipeline.
    Returns 409 if the campaign is not in ``draft`` status (i.e. it has already
    been launched or is in a different state).
    """
    if campaign.status != CampaignStatus.DRAFT:
        raise HTTPException(
            status_code=409,
            detail=f"Campaign is in '{campaign.status.value}' state and cannot be launched. Only draft campaigns can be launched.",
        )

    # Dispatch the pipeline to the configured executor (runs in background)
    await get_executor().dispatch(WorkflowJob(campaign_id=campaign.id, action="start_pipeline"))
    logger.info("Campaign %s launched — pipeline dispatched", campaign.id)

    return WorkflowActionResponse(
        message="Campaign launched. Pipeline is running — connect to WebSocket for live updates.",
        campaign_id=campaign.id,
    )


@router.post("/campaigns/{campaign_id}/clarify", response_model=WorkflowActionResponse)
async def submit_clarification(
    response: ClarificationResponse,
    campaign: Campaign = Depends(get_campaign_for_write),
) -> WorkflowActionResponse:
    """Submit answers to strategy clarification questions."""
    workflow = get_workflow_service()
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
    logger.info("content-approve called for campaign=%s pieces=%d reject=%s",
                campaign.id, len(response.pieces), response.reject_campaign)
    workflow = get_workflow_service()
    try:
        await workflow.submit_content_approval(campaign.id, response)
    except ValueError:
        raise HTTPException(status_code=404, detail="Campaign not found")
    except Exception as exc:
        logger.exception("content-approve FAILED for campaign=%s: %s", campaign.id, exc)
        raise HTTPException(status_code=500, detail=f"Content approval failed: {exc}")

    return WorkflowActionResponse(message="Content approval submitted", campaign_id=campaign.id)


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
    workflow = get_workflow_service()
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
    except (WorkflowConflictError, ConcurrentUpdateError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


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
    workflow = get_workflow_service()
    try:
        result = await workflow.update_piece_notes(campaign.id, piece_index, body.notes)
        return PieceNotesResponse(
            campaign_id=result["campaign_id"],
            piece_index=result["piece_index"],
            message=result["message"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (WorkflowConflictError, ConcurrentUpdateError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/campaigns/{campaign_id}/resume", response_model=WorkflowActionResponse)
async def resume_campaign(
    campaign_id: str,
    campaign: Campaign = Depends(get_campaign_for_write),
) -> WorkflowActionResponse:
    """Resume a pipeline that was interrupted (server restart, timeout, etc.)."""
    await get_executor().dispatch(WorkflowJob(campaign_id=campaign.id, action="resume_pipeline"))
    return WorkflowActionResponse(message="Pipeline resume initiated", campaign_id=campaign.id)


@router.post("/campaigns/{campaign_id}/retry", response_model=WorkflowActionResponse)
async def retry_campaign(
    campaign_id: str,
    campaign: Campaign = Depends(get_campaign_for_write),
) -> WorkflowActionResponse:
    """Retry the current failed stage of a campaign."""
    await get_executor().dispatch(WorkflowJob(campaign_id=campaign.id, action="retry_stage"))
    return WorkflowActionResponse(message="Stage retry initiated", campaign_id=campaign.id)

