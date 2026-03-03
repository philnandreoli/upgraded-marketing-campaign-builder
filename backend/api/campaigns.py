"""
Campaign REST API routes.

Endpoints:
  POST   /api/campaigns               — Create a campaign from a brief and start the pipeline
  GET    /api/campaigns                — List all campaigns
  GET    /api/campaigns/{id}           — Get a single campaign
  DELETE /api/campaigns/{id}           — Delete a campaign
  POST   /api/campaigns/{id}/clarify   — Submit answers to strategy clarification questions
  POST   /api/campaigns/{id}/content-approve — Submit per-piece content approval decisions
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response

from backend.agents.coordinator_agent import CoordinatorAgent
from backend.models.campaign import Campaign, CampaignBrief
from backend.models.messages import ClarificationResponse, ContentApprovalResponse, HumanReviewResponse
from backend.models.user import User
from backend.services.auth import get_current_user
from backend.services.campaign_store import get_campaign_store
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

def _require_owner(campaign: Campaign, user: Optional[User]) -> None:
    """Raise 404 if the campaign does not belong to the requesting user.

    When auth is disabled (user is None) all campaigns are accessible.
    We deliberately return 404 (not 403) to avoid leaking campaign existence.
    """
    if user is not None and campaign.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Campaign not found")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/campaigns", status_code=201)
async def create_campaign(
    brief: CampaignBrief,
    background_tasks: BackgroundTasks,
    user: Optional[User] = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new campaign and kick off the agent pipeline in the background."""
    store = get_campaign_store()
    campaign = await store.create(brief, owner_id=user.id if user else None)

    coordinator = _get_coordinator()

    # Run the pipeline in the background so the HTTP response returns immediately
    background_tasks.add_task(_run_pipeline, coordinator, campaign)

    return {
        "id": campaign.id,
        "status": campaign.status.value,
        "message": "Campaign created. Pipeline is running — connect to WebSocket for live updates.",
    }


async def _run_pipeline(coordinator: CoordinatorAgent, campaign: Campaign) -> None:
    """Wrapper executed as a background task."""
    try:
        await coordinator.run_pipeline(campaign)
    except Exception:
        logger.exception("Pipeline crashed for campaign %s", campaign.id)


@router.get("/campaigns")
async def list_campaigns(
    user: Optional[User] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return campaigns visible to the current user (summary view)."""
    store = get_campaign_store()
    if user is not None:
        campaigns = await store.list_by_owner(user.id)
    else:
        campaigns = await store.list_all()
    return [
        {
            "id": c.id,
            "status": c.status.value,
            "product_or_service": c.brief.product_or_service,
            "goal": c.brief.goal,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in campaigns
    ]


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the full campaign document."""
    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    _require_owner(campaign, user)
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
    _require_owner(campaign, user)
    await store.delete(campaign_id)
    return Response(status_code=204)


@router.post("/campaigns/{campaign_id}/clarify")
async def submit_clarification(
    campaign_id: str,
    response: ClarificationResponse,
    user: Optional[User] = Depends(get_current_user),
) -> dict[str, str]:
    """Submit answers to strategy clarification questions."""
    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    _require_owner(campaign, user)

    response.campaign_id = campaign_id

    coordinator = _get_coordinator()
    await coordinator.submit_clarification(response)

    return {"message": "Clarification submitted", "campaign_id": campaign_id}


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


@router.post("/campaigns/{campaign_id}/content-approve")
async def submit_content_approval(
    campaign_id: str,
    response: ContentApprovalResponse,
    user: Optional[User] = Depends(get_current_user),
) -> dict[str, str]:
    """Submit per-piece content approval decisions."""
    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    _require_owner(campaign, user)

    response.campaign_id = campaign_id

    coordinator = _get_coordinator()
    await coordinator.submit_content_approval(response)

    return {"message": "Content approval submitted", "campaign_id": campaign_id}
