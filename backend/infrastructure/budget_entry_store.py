"""PostgreSQL-backed budget entry store."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, update as sa_update, delete as sa_delete

from backend.infrastructure.database import BudgetEntryRow, CampaignRow, async_session
from backend.models.budget import (
    BudgetEntry,
    BudgetEntryType,
    BudgetSummary,
    WorkspaceBudgetOverview,
    WorkspaceBudgetOverviewItem,
)


class BudgetEntryStore:
    """Budget entry repository backed by PostgreSQL."""

    async def create(self, entry: BudgetEntry) -> BudgetEntry:
        row = BudgetEntryRow(
            id=entry.id,
            campaign_id=entry.campaign_id,
            entry_type=entry.entry_type.value,
            amount=entry.amount,
            currency=entry.currency,
            category=entry.category,
            description=entry.description,
            entry_date=datetime.combine(entry.entry_date, datetime.min.time()),
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
        return entry

    async def get(self, entry_id: str) -> Optional[BudgetEntry]:
        async with async_session() as session:
            row = await session.get(BudgetEntryRow, entry_id)
            if row is None:
                return None
            return _row_to_model(row)

    async def list_by_campaign(
        self,
        campaign_id: str,
        entry_type: Optional[BudgetEntryType] = None,
    ) -> list[BudgetEntry]:
        async with async_session() as session:
            stmt = (
                select(BudgetEntryRow)
                .where(BudgetEntryRow.campaign_id == campaign_id)
                .order_by(BudgetEntryRow.entry_date.desc(), BudgetEntryRow.created_at.desc())
            )
            if entry_type is not None:
                stmt = stmt.where(BudgetEntryRow.entry_type == entry_type.value)
            result = await session.execute(stmt)
            return [_row_to_model(row) for row in result.scalars().all()]

    async def update(
        self,
        entry_id: str,
        *,
        amount: Decimal,
        currency: str,
        category: Optional[str],
        description: Optional[str],
        entry_date: datetime,
    ) -> BudgetEntry:
        now = datetime.utcnow()
        async with async_session() as session:
            result = await session.execute(
                sa_update(BudgetEntryRow)
                .where(BudgetEntryRow.id == entry_id)
                .values(
                    amount=amount,
                    currency=currency,
                    category=category,
                    description=description,
                    entry_date=entry_date,
                    updated_at=now,
                )
                .returning(BudgetEntryRow)
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise ValueError(f"Budget entry {entry_id!r} not found")
            await session.commit()
            return _row_to_model(row)

    async def delete(self, entry_id: str) -> bool:
        async with async_session() as session:
            result = await session.execute(
                sa_delete(BudgetEntryRow).where(BudgetEntryRow.id == entry_id)
            )
            await session.commit()
            return result.rowcount > 0

    async def get_summary(
        self,
        campaign_id: str,
        *,
        alert_threshold_pct: float = 0.8,
    ) -> BudgetSummary:
        async with async_session() as session:
            totals = await session.execute(
                select(
                    func.max(BudgetEntryRow.currency).label("currency"),
                    func.coalesce(
                        func.sum(BudgetEntryRow.amount).filter(
                            BudgetEntryRow.entry_type == BudgetEntryType.PLANNED.value
                        ),
                        0,
                    ).label("planned_total"),
                    func.coalesce(
                        func.sum(BudgetEntryRow.amount).filter(
                            BudgetEntryRow.entry_type == BudgetEntryType.ACTUAL.value
                        ),
                        0,
                    ).label("actual_total"),
                ).where(BudgetEntryRow.campaign_id == campaign_id)
            )
            currency, planned_total, actual_total = totals.one()
            planned = Decimal(planned_total or 0).quantize(Decimal("0.01"))
            actual = Decimal(actual_total or 0).quantize(Decimal("0.01"))
            resolved_currency = currency or "USD"
            spent_ratio = float(actual / planned) if planned > 0 else 0.0
            return BudgetSummary(
                campaign_id=campaign_id,
                currency=resolved_currency,
                planned_total=planned,
                actual_total=actual,
                variance=(actual - planned).quantize(Decimal("0.01")),
                spent_ratio=spent_ratio,
                alert_threshold_pct=alert_threshold_pct,
                is_alert_triggered=planned > 0 and spent_ratio >= alert_threshold_pct,
            )

    async def get_workspace_overview(
        self,
        workspace_id: str,
        *,
        alert_threshold_pct: float = 0.8,
    ) -> WorkspaceBudgetOverview:
        async with async_session() as session:
            campaign_rows = await session.execute(
                select(CampaignRow.id, CampaignRow.data).where(
                    CampaignRow.workspace_id == workspace_id
                )
            )
            campaigns = campaign_rows.all()
            if not campaigns:
                return WorkspaceBudgetOverview(workspace_id=workspace_id, currency="USD")

            campaign_ids = [campaign_id for campaign_id, _ in campaigns]
            totals = await session.execute(
                select(
                    BudgetEntryRow.campaign_id,
                    func.max(BudgetEntryRow.currency).label("currency"),
                    func.coalesce(
                        func.sum(BudgetEntryRow.amount).filter(
                            BudgetEntryRow.entry_type == BudgetEntryType.PLANNED.value
                        ),
                        0,
                    ).label("planned_total"),
                    func.coalesce(
                        func.sum(BudgetEntryRow.amount).filter(
                            BudgetEntryRow.entry_type == BudgetEntryType.ACTUAL.value
                        ),
                        0,
                    ).label("actual_total"),
                )
                .where(BudgetEntryRow.campaign_id.in_(campaign_ids))
                .group_by(BudgetEntryRow.campaign_id)
            )
            totals_map: dict[str, tuple[str, Decimal, Decimal]] = {}
            for row in totals.all():
                totals_map[row.campaign_id] = (
                    row.currency or "USD",
                    Decimal(row.planned_total or 0).quantize(Decimal("0.01")),
                    Decimal(row.actual_total or 0).quantize(Decimal("0.01")),
                )

            items: list[WorkspaceBudgetOverviewItem] = []
            planned_total = Decimal("0.00")
            actual_total = Decimal("0.00")
            currency = "USD"

            for campaign_id, campaign_json in campaigns:
                campaign_name = campaign_id
                try:
                    campaign_name = (
                        BudgetEntryStore._campaign_name_from_json(campaign_json)
                        or campaign_id
                    )
                except Exception:
                    campaign_name = campaign_id

                campaign_currency, campaign_planned, campaign_actual = totals_map.get(
                    campaign_id, ("USD", Decimal("0.00"), Decimal("0.00"))
                )
                if campaign_planned > 0 or campaign_actual > 0:
                    currency = campaign_currency
                summary = BudgetSummary(
                    campaign_id=campaign_id,
                    currency=campaign_currency,
                    planned_total=campaign_planned,
                    actual_total=campaign_actual,
                    variance=(campaign_actual - campaign_planned).quantize(Decimal("0.01")),
                    spent_ratio=float(campaign_actual / campaign_planned)
                    if campaign_planned > 0
                    else 0.0,
                    alert_threshold_pct=alert_threshold_pct,
                    is_alert_triggered=campaign_planned > 0
                    and float(campaign_actual / campaign_planned) >= alert_threshold_pct,
                )
                planned_total += campaign_planned
                actual_total += campaign_actual
                items.append(
                    WorkspaceBudgetOverviewItem(
                        campaign_id=campaign_id,
                        campaign_name=campaign_name,
                        summary=summary,
                    )
                )

            spent_ratio = float(actual_total / planned_total) if planned_total > 0 else 0.0
            return WorkspaceBudgetOverview(
                workspace_id=workspace_id,
                currency=currency,
                campaign_count=len(campaigns),
                planned_total=planned_total.quantize(Decimal("0.01")),
                actual_total=actual_total.quantize(Decimal("0.01")),
                variance=(actual_total - planned_total).quantize(Decimal("0.01")),
                spent_ratio=spent_ratio,
                items=items,
            )

    @staticmethod
    def _campaign_name_from_json(campaign_json: str) -> Optional[str]:
        import json

        data = json.loads(campaign_json)
        brief = data.get("brief") or {}
        return brief.get("product_or_service")


def _row_to_model(row: BudgetEntryRow) -> BudgetEntry:
    return BudgetEntry(
        id=row.id,
        campaign_id=row.campaign_id,
        entry_type=BudgetEntryType(row.entry_type),
        amount=Decimal(row.amount).quantize(Decimal("0.01")),
        currency=row.currency,
        category=row.category,
        description=row.description,
        entry_date=row.entry_date.date(),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


_store: BudgetEntryStore | None = None


def get_budget_entry_store() -> BudgetEntryStore:
    global _store
    if _store is None:
        _store = BudgetEntryStore()
    return _store
