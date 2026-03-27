"""Campaign budget entry and summary routes."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from backend.api.workspaces import WorkspaceAction, _authorize_workspace
from backend.apps.api.dependencies import get_campaign_for_read, get_campaign_for_write
from backend.apps.api.schemas.budget import (
    BudgetEntryResponse,
    BudgetSummaryResponse,
    CreateBudgetEntryRequest,
    UpdateBudgetEntryRequest,
    WorkspaceBudgetOverviewItemResponse,
    WorkspaceBudgetOverviewResponse,
)
from backend.infrastructure.auth import get_current_user
from backend.infrastructure.budget_entry_store import get_budget_entry_store
from backend.infrastructure.campaign_store import get_campaign_store
from backend.models.budget import BudgetEntry, BudgetEntryType
from backend.models.campaign import Campaign
from backend.models.user import User

router = APIRouter(tags=["budget"])


@router.post(
    "/campaigns/{campaign_id}/budget-entries",
    response_model=BudgetEntryResponse,
    status_code=201,
)
async def create_budget_entry(
    campaign_id: str,
    body: CreateBudgetEntryRequest,
    campaign: Campaign = Depends(get_campaign_for_write),
) -> BudgetEntryResponse:
    store = get_budget_entry_store()
    entry = BudgetEntry(
        campaign_id=campaign.id,
        entry_type=body.entry_type,
        amount=body.amount,
        currency=body.currency.upper(),
        category=body.category,
        description=body.description,
        entry_date=body.entry_date,
    )
    created = await store.create(entry)
    return BudgetEntryResponse.model_validate(created.model_dump())


@router.get(
    "/campaigns/{campaign_id}/budget-entries",
    response_model=list[BudgetEntryResponse],
)
async def list_budget_entries(
    campaign_id: str,
    campaign: Campaign = Depends(get_campaign_for_read),
    entry_type: Optional[BudgetEntryType] = Query(
        default=None, description="Optional filter for planned or actual entries."
    ),
) -> list[BudgetEntryResponse]:
    store = get_budget_entry_store()
    entries = await store.list_by_campaign(campaign.id, entry_type=entry_type)
    return [BudgetEntryResponse.model_validate(e.model_dump()) for e in entries]


@router.patch(
    "/campaigns/{campaign_id}/budget-entries/{entry_id}",
    response_model=BudgetEntryResponse,
)
async def update_budget_entry(
    campaign_id: str,
    entry_id: str,
    body: UpdateBudgetEntryRequest,
    campaign: Campaign = Depends(get_campaign_for_write),
) -> BudgetEntryResponse:
    store = get_budget_entry_store()
    existing = await store.get(entry_id)
    if existing is None or existing.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Budget entry not found")
    updated = await store.update(
        entry_id,
        amount=body.amount,
        currency=body.currency.upper(),
        category=body.category,
        description=body.description,
        entry_date=datetime.combine(body.entry_date, datetime.min.time()),
    )
    return BudgetEntryResponse.model_validate(updated.model_dump())


@router.delete(
    "/campaigns/{campaign_id}/budget-entries/{entry_id}",
    status_code=204,
    response_class=Response,
)
async def delete_budget_entry(
    campaign_id: str,
    entry_id: str,
    campaign: Campaign = Depends(get_campaign_for_write),
) -> Response:
    store = get_budget_entry_store()
    existing = await store.get(entry_id)
    if existing is None or existing.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Budget entry not found")
    await store.delete(entry_id)
    return Response(status_code=204)


@router.get(
    "/campaigns/{campaign_id}/budget-summary",
    response_model=BudgetSummaryResponse,
)
async def get_campaign_budget_summary(
    campaign_id: str,
    campaign: Campaign = Depends(get_campaign_for_read),
    alert_threshold_pct: float = Query(
        default=0.8, ge=0.0, description="Alert threshold as a spend ratio over planned."
    ),
) -> BudgetSummaryResponse:
    store = get_budget_entry_store()
    summary = await store.get_summary(
        campaign.id, alert_threshold_pct=alert_threshold_pct
    )
    return BudgetSummaryResponse.model_validate(summary.model_dump())


@router.get(
    "/budget-overview",
    response_model=WorkspaceBudgetOverviewResponse,
)
async def get_workspace_budget_overview(
    workspace_id: str,
    user: Optional[User] = Depends(get_current_user),
    alert_threshold_pct: float = Query(
        default=0.8, ge=0.0, description="Alert threshold as a spend ratio over planned."
    ),
) -> WorkspaceBudgetOverviewResponse:
    campaign_store = get_campaign_store()
    workspace = await campaign_store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.READ, campaign_store)

    store = get_budget_entry_store()
    overview = await store.get_workspace_overview(
        workspace_id, alert_threshold_pct=alert_threshold_pct
    )
    return WorkspaceBudgetOverviewResponse(
        workspace_id=overview.workspace_id,
        currency=overview.currency,
        campaign_count=overview.campaign_count,
        planned_total=overview.planned_total,
        actual_total=overview.actual_total,
        variance=overview.variance,
        spent_ratio=overview.spent_ratio,
        items=[
            WorkspaceBudgetOverviewItemResponse(
                campaign_id=item.campaign_id,
                campaign_name=item.campaign_name,
                summary=BudgetSummaryResponse.model_validate(item.summary.model_dump()),
            )
            for item in overview.items
        ],
    )
