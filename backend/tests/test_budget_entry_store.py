from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.infrastructure.budget_entry_store import BudgetEntryStore, get_budget_entry_store
from backend.infrastructure.database import BudgetEntryRow, CampaignRow
from backend.models.budget import BudgetEntry, BudgetEntryType


@pytest.fixture
async def store_with_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: CampaignRow.metadata.create_all(
                sync_conn,
                tables=[CampaignRow.__table__, BudgetEntryRow.__table__],
            )
        )

    async with session_factory() as session:
        now = datetime.utcnow()
        session.add_all(
            [
                CampaignRow(
                    id="campaign-1",
                    owner_id=None,
                    status="draft",
                    data='{"id":"campaign-1","brief":{"product_or_service":"Campaign One"}}',
                    created_at=now,
                    updated_at=now,
                    workspace_id="ws-1",
                    version=1,
                ),
                CampaignRow(
                    id="campaign-2",
                    owner_id=None,
                    status="draft",
                    data='{"id":"campaign-2","brief":{"product_or_service":"Campaign Two"}}',
                    created_at=now,
                    updated_at=now,
                    workspace_id="ws-1",
                    version=1,
                ),
            ]
        )
        await session.commit()

    with patch("backend.infrastructure.budget_entry_store.async_session", session_factory):
        yield BudgetEntryStore()

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_get_update_delete_budget_entry(store_with_db):
    entry = BudgetEntry(
        id="entry-1",
        campaign_id="campaign-1",
        entry_type=BudgetEntryType.PLANNED,
        amount=Decimal("100.00"),
        currency="USD",
        category="ads",
        description="planned ads",
        entry_date=date(2026, 1, 10),
    )

    created = await store_with_db.create(entry)
    assert created.id == "entry-1"

    fetched = await store_with_db.get("entry-1")
    assert fetched is not None
    assert fetched.amount == Decimal("100.00")

    updated = await store_with_db.update(
        "entry-1",
        amount=Decimal("125.00"),
        currency="USD",
        category="ads",
        description="updated",
        entry_date=datetime(2026, 1, 11),
    )
    assert updated.amount == Decimal("125.00")
    assert updated.entry_date == date(2026, 1, 11)

    deleted = await store_with_db.delete("entry-1")
    assert deleted is True
    assert await store_with_db.get("entry-1") is None


@pytest.mark.asyncio
async def test_summary_computes_totals_and_alert(store_with_db):
    await store_with_db.create(
        BudgetEntry(
            campaign_id="campaign-1",
            entry_type=BudgetEntryType.PLANNED,
            amount=Decimal("100.00"),
            currency="USD",
            entry_date=date(2026, 1, 1),
        )
    )
    await store_with_db.create(
        BudgetEntry(
            campaign_id="campaign-1",
            entry_type=BudgetEntryType.ACTUAL,
            amount=Decimal("90.00"),
            currency="USD",
            entry_date=date(2026, 1, 2),
        )
    )

    summary = await store_with_db.get_summary("campaign-1", alert_threshold_pct=0.8)
    assert summary.planned_total == Decimal("100.00")
    assert summary.actual_total == Decimal("90.00")
    assert summary.variance == Decimal("-10.00")
    assert summary.is_alert_triggered is True


@pytest.mark.asyncio
async def test_workspace_overview_rollup(store_with_db):
    await store_with_db.create(
        BudgetEntry(
            campaign_id="campaign-1",
            entry_type=BudgetEntryType.PLANNED,
            amount=Decimal("100.00"),
            currency="USD",
            entry_date=date(2026, 1, 1),
        )
    )
    await store_with_db.create(
        BudgetEntry(
            campaign_id="campaign-1",
            entry_type=BudgetEntryType.ACTUAL,
            amount=Decimal("80.00"),
            currency="USD",
            entry_date=date(2026, 1, 2),
        )
    )
    await store_with_db.create(
        BudgetEntry(
            campaign_id="campaign-2",
            entry_type=BudgetEntryType.PLANNED,
            amount=Decimal("50.00"),
            currency="USD",
            entry_date=date(2026, 1, 3),
        )
    )

    overview = await store_with_db.get_workspace_overview("ws-1")
    assert overview.workspace_id == "ws-1"
    assert overview.campaign_count == 2
    assert overview.planned_total == Decimal("150.00")
    assert overview.actual_total == Decimal("80.00")
    assert len(overview.items) == 2


def test_get_budget_entry_store_singleton():
    with patch("backend.infrastructure.budget_entry_store._store", None):
        first = get_budget_entry_store()
        second = get_budget_entry_store()

    assert first is second
