"""
Campaign Workflow Service — thin service layer between API routes and orchestration.

Wraps the CampaignStore so that route handlers only deal with HTTP concerns,
while business/workflow rules live here.  Pipeline execution is handled by the
WorkflowExecutor abstraction; this service only writes signals and stores state.
"""

from __future__ import annotations

from typing import Any, Optional

from backend.models.campaign import Campaign, CampaignBrief, CampaignStatus, ContentApprovalStatus
from backend.models.messages import ClarificationResponse, ContentApprovalResponse
from backend.models.user import User
from backend.services.campaign_store import CampaignStore, get_campaign_store
from backend.services.exceptions import WorkflowConflictError
from backend.services.workflow_signal_store import WorkflowSignalStore, SignalType, get_workflow_signal_store

__all__ = ["CampaignWorkflowService", "WorkflowConflictError", "get_workflow_service"]


class CampaignWorkflowService:
    """Handles campaign state operations (signals, decisions, notes).

    Pipeline execution (start / resume / retry) is handled by the
    WorkflowExecutor layer and is no longer part of this service.
    """

    def __init__(self, store: CampaignStore, signal_store: WorkflowSignalStore | None = None) -> None:
        self._store = store
        self._signal_store = signal_store if signal_store is not None else get_workflow_signal_store()

    async def create_campaign(self, brief: CampaignBrief, user: User | None) -> Campaign:
        """Persist a new campaign and return it."""
        return await self._store.create(brief, owner_id=user.id if user else None)

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
        await self._signal_store.write_signal(
            campaign_id,
            SignalType.CLARIFICATION_RESPONSE,
            response.model_dump(mode="json"),
        )

    async def submit_content_approval(
        self, campaign_id: str, response: ContentApprovalResponse
    ) -> None:
        """Write the content approval signal for the running coordinator to pick up."""
        campaign = await self._store.get(campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign {campaign_id} not found")
        response.campaign_id = campaign_id
        await self._signal_store.write_signal(
            campaign_id,
            SignalType.CONTENT_APPROVAL,
            response.model_dump(mode="json"),
        )

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


def get_workflow_service() -> CampaignWorkflowService:
    """Return the shared CampaignWorkflowService instance."""
    global _workflow_service
    if _workflow_service is None:
        _workflow_service = CampaignWorkflowService(store=get_campaign_store())
    return _workflow_service
