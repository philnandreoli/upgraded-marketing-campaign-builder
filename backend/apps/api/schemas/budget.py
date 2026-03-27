"""Pydantic request/response schemas for budget tracking endpoints."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from backend.models.budget import BudgetEntryType


class CreateBudgetEntryRequest(BaseModel):
    entry_type: BudgetEntryType
    amount: Decimal = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    category: Optional[str] = None
    description: Optional[str] = None
    entry_date: date


class UpdateBudgetEntryRequest(BaseModel):
    amount: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    category: Optional[str] = None
    description: Optional[str] = None
    entry_date: date


class BudgetEntryResponse(BaseModel):
    id: str
    campaign_id: str
    entry_type: BudgetEntryType
    amount: Decimal
    currency: str
    category: Optional[str]
    description: Optional[str]
    entry_date: date
    created_at: datetime
    updated_at: datetime


class BudgetSummaryResponse(BaseModel):
    campaign_id: str
    currency: str
    planned_total: Decimal
    actual_total: Decimal
    variance: Decimal
    spent_ratio: float
    alert_threshold_pct: float
    is_alert_triggered: bool


class WorkspaceBudgetOverviewItemResponse(BaseModel):
    campaign_id: str
    campaign_name: str
    summary: BudgetSummaryResponse


class WorkspaceBudgetOverviewResponse(BaseModel):
    workspace_id: str
    currency: str
    campaign_count: int
    planned_total: Decimal
    actual_total: Decimal
    variance: Decimal
    spent_ratio: float
    items: list[WorkspaceBudgetOverviewItemResponse]
