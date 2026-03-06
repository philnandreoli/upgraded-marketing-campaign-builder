"""
Campaign Workflow Service — thin service layer between API routes and orchestration.

Wraps the CampaignStore and CoordinatorAgent so that route handlers only deal
with HTTP concerns, while business/workflow rules live here.
"""

from __future__ import annotations

from backend.agents.coordinator_agent import CoordinatorAgent
from backend.models.campaign import Campaign, CampaignBrief, CampaignStatus
from backend.models.messages import ClarificationResponse
from backend.models.user import User
from backend.services.campaign_store import CampaignStore, get_campaign_store


class WorkflowConflictError(Exception):
    """Raised when a workflow action is not valid for the current campaign status."""


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
