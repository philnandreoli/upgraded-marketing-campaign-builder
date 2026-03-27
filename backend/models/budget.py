"""Budget data models for campaign spend tracking and forecasting."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BudgetEntryType(str, Enum):
    """Supported budget entry types."""

    PLANNED = "planned"
    ACTUAL = "actual"


class BudgetEntry(BaseModel):
    """A single planned or actual spend entry for a campaign."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str
    entry_type: BudgetEntryType
    amount: Decimal = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    category: Optional[str] = None
    description: Optional[str] = None
    entry_date: date
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class BudgetSummary(BaseModel):
    """Aggregate budget summary for a single campaign."""

    campaign_id: str
    currency: str
    planned_total: Decimal = Field(default=Decimal("0.00"))
    actual_total: Decimal = Field(default=Decimal("0.00"))
    variance: Decimal = Field(default=Decimal("0.00"))
    spent_ratio: float = 0.0
    alert_threshold_pct: float = 0.8
    is_alert_triggered: bool = False


class WorkspaceBudgetOverviewItem(BaseModel):
    """Budget summary entry for one campaign in a workspace overview."""

    campaign_id: str
    campaign_name: str
    summary: BudgetSummary


class WorkspaceBudgetOverview(BaseModel):
    """Workspace-level budget rollup."""

    workspace_id: str
    currency: str
    campaign_count: int = 0
    planned_total: Decimal = Field(default=Decimal("0.00"))
    actual_total: Decimal = Field(default=Decimal("0.00"))
    variance: Decimal = Field(default=Decimal("0.00"))
    spent_ratio: float = 0.0
    items: list[WorkspaceBudgetOverviewItem] = Field(default_factory=list)
