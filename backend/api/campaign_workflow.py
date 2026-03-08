"""
Campaign workflow command routes.

Endpoints:
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

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from backend.models.campaign import Campaign
from backend.models.messages import ClarificationResponse, ContentApprovalResponse, HumanReviewResponse
from backend.models.user import User
from backend.infrastructure.auth import get_current_user
from backend.application.campaign_workflow_service import WorkflowConflictError
from backend.infrastructure.workflow_executor import get_executor, WorkflowJob

# Access shared state through the campaigns module so that test patches on
# backend.api.campaigns.* continue to work without modification.
import backend.api.campaigns as _cam

from backend.api.campaigns import (
    WorkflowActionResponse,
    PieceDecisionRequest,
    PieceDecisionResponse,
    UpdatePieceNotesRequest,
    PieceNotesResponse,
    get_campaign_for_write,
)

router = APIRouter(tags=["campaigns"])


@router.post("/campaigns/{campaign_id}/clarify", response_model=WorkflowActionResponse)
async def submit_clarification(
    response: ClarificationResponse,
    campaign: Campaign = Depends(get_campaign_for_write),
) -> WorkflowActionResponse:
    """Submit answers to strategy clarification questions."""
    workflow = _cam.get_workflow_service()
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
    workflow = _cam.get_workflow_service()
    try:
        await workflow.submit_content_approval(campaign.id, response)
    except ValueError:
        raise HTTPException(status_code=404, detail="Campaign not found")

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
    workflow = _cam.get_workflow_service()
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
    workflow = _cam.get_workflow_service()
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
