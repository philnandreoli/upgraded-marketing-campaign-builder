"""
Campaign Workflow Service — thin service layer between API routes and orchestration.

Wraps the CampaignStore and CoordinatorAgent so that route handlers only deal
with HTTP concerns, while business/workflow rules live here.
"""

from __future__ import annotations

from typing import Any, Optional

from backend.agents.coordinator_agent import CoordinatorAgent
from backend.models.campaign import Campaign, CampaignBrief, CampaignStatus, ContentApprovalStatus
from backend.models.messages import ClarificationResponse, ContentApprovalResponse
from backend.models.user import User
from backend.services.campaign_store import CampaignStore, get_campaign_store
from backend.services.exceptions import WorkflowConflictError

__all__ = ["CampaignWorkflowService", "WorkflowConflictError", "get_workflow_service"]


class CampaignWorkflowService:
    """Orchestrates campaign creation and pipeline execution."""

    def __init__(self, store: CampaignStore, coordinator: CoordinatorAgent) -> None:
        self._store = store
        self._coordinator = coordinator

    async def create_campaign(self, brief: CampaignBrief, user: User | None) -> Campaign:
        """Persist a new campaign and return it."""
        return await self._store.create(brief, owner_id=user.id if user else None)

    async def start_pipeline(self, campaign_id: str) -> None:
        """Look up a campaign and hand it off to the coordinator pipeline."""
        campaign = await self._store.get(campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign {campaign_id} not found")
        await self._coordinator.run_pipeline(campaign)

    async def resume_pipeline(self, campaign_id: str) -> None:
        """Resume a previously interrupted pipeline from its last checkpoint."""
        await self._coordinator.resume_pipeline(campaign_id)

    async def retry_current_stage(self, campaign_id: str) -> None:
        """Clear the current stage error and re-run that stage."""
        await self._coordinator.retry_current_stage(campaign_id)

    async def submit_clarification(
        self, campaign_id: str, response: ClarificationResponse
    ) -> None:
        """Validate campaign status and forward clarification answers to the coordinator."""
        campaign = await self._store.get(campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign {campaign_id} not found")
        if campaign.status != CampaignStatus.CLARIFICATION:
            raise WorkflowConflictError(
                f"Campaign is in '{campaign.status.value}', not 'clarification'"
            )
        response.campaign_id = campaign_id
        await self._coordinator.submit_clarification(response)

    async def submit_content_approval(
        self, campaign_id: str, response: ContentApprovalResponse
    ) -> None:
        """Forward content approval decisions to the coordinator."""
        campaign = await self._store.get(campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign {campaign_id} not found")
        response.campaign_id = campaign_id
        await self._coordinator.submit_content_approval(response)

    async def update_piece_decision(
        self,
        campaign_id: str,
        piece_index: int,
        approved: bool,
        edited_content: Optional[str],
        notes: str,
    ) -> dict[str, Any]:
        """Persist an approve/reject decision for a single content piece.

        Raises ValueError if the campaign or piece does not exist, and
        WorkflowConflictError if the campaign is not in content_approval status
        or if an attempt is made to reject an already-approved piece.
        """
        campaign = await self._store.get(campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign {campaign_id} not found")
        if campaign.status != CampaignStatus.CONTENT_APPROVAL:
            raise WorkflowConflictError("Campaign is not in content_approval status")
        if campaign.content is None or not (0 <= piece_index < len(campaign.content.pieces)):
            raise ValueError("Content piece not found")

        piece = campaign.content.pieces[piece_index]

        # Approved pieces are immutable — cannot be un-approved via this endpoint.
        if piece.approval_status == ContentApprovalStatus.APPROVED and not approved:
            raise WorkflowConflictError("Cannot reject an already-approved piece")

        if approved:
            piece.approval_status = ContentApprovalStatus.APPROVED
            if edited_content is not None:
                piece.human_edited_content = edited_content
            if notes:
                piece.human_notes = notes
        else:
            piece.approval_status = ContentApprovalStatus.REJECTED
            if edited_content is not None:
                piece.human_edited_content = edited_content
            piece.human_notes = notes

        await self._store.update(campaign)

        return {
            "message": "Piece decision saved",
            "campaign_id": campaign_id,
            "piece_index": piece_index,
            "approval_status": piece.approval_status,
        }

    async def update_piece_notes(
        self, campaign_id: str, piece_index: int, notes: str
    ) -> dict[str, Any]:
        """Update human_notes on an already-approved content piece.

        Raises ValueError if the campaign or piece does not exist, and
        WorkflowConflictError if the piece has not yet been approved.
        """
        campaign = await self._store.get(campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign {campaign_id} not found")
        if campaign.content is None or not (0 <= piece_index < len(campaign.content.pieces)):
            raise ValueError("Content piece not found")

        piece = campaign.content.pieces[piece_index]
        if piece.approval_status != ContentApprovalStatus.APPROVED:
            raise WorkflowConflictError("Notes can only be updated on approved content pieces")

        piece.human_notes = notes
        await self._store.update(campaign)

        return {"message": "Notes updated", "campaign_id": campaign_id, "piece_index": piece_index}


# ---------------------------------------------------------------------------
# Module-level factory (mirrors the pattern used for get_campaign_store)
# ---------------------------------------------------------------------------

_workflow_service: CampaignWorkflowService | None = None


def get_workflow_service(coordinator: CoordinatorAgent | None = None) -> CampaignWorkflowService:
    """Return the shared CampaignWorkflowService instance.

    *coordinator* is accepted as an optional parameter so that the API layer
    can inject its singleton coordinator without this module needing to own
    the broadcast callback setup.
    """
    global _workflow_service
    if _workflow_service is None:
        if coordinator is None:
            raise RuntimeError(
                "get_workflow_service() called without a coordinator before the service was initialised. "
                "Pass the coordinator on first call."
            )
        _workflow_service = CampaignWorkflowService(
            store=get_campaign_store(),
            coordinator=coordinator,
        )
    return _workflow_service
