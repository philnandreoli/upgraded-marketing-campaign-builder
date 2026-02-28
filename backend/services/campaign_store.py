"""
PostgreSQL-backed campaign store.

Persists campaigns as JSON documents in a single 'campaigns' table.
The public API is intentionally synchronous-looking — each method runs
a short async DB call via the shared session factory.  Because FastAPI
route handlers and background tasks are already async, the callers can
simply ``await`` these methods.
"""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import delete as sa_delete, select

from backend.models.campaign import Campaign, CampaignBrief
from backend.services.database import CampaignRow, async_session


class CampaignStore:
    """Campaign repository backed by PostgreSQL."""

    # ------------------------------------------------------------------
    # CRUD — all async
    # ------------------------------------------------------------------

    async def create(self, brief: CampaignBrief) -> Campaign:
        """Create a new campaign from a brief and persist it."""
        campaign = Campaign(brief=brief)
        row = CampaignRow(
            id=campaign.id,
            status=campaign.status.value,
            data=campaign.model_dump_json(),
            created_at=campaign.created_at,
            updated_at=campaign.updated_at,
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
        return campaign

    async def get(self, campaign_id: str) -> Optional[Campaign]:
        async with async_session() as session:
            row = await session.get(CampaignRow, campaign_id)
            if row is None:
                return None
            return Campaign.model_validate_json(row.data)

    async def update(self, campaign: Campaign) -> Campaign:
        async with async_session() as session:
            row = await session.get(CampaignRow, campaign.id)
            if row is None:
                # First time persisting — insert instead
                row = CampaignRow(
                    id=campaign.id,
                    status=campaign.status.value,
                    data=campaign.model_dump_json(),
                    created_at=campaign.created_at,
                    updated_at=campaign.updated_at,
                )
                session.add(row)
            else:
                row.status = campaign.status.value
                row.data = campaign.model_dump_json()
                row.updated_at = campaign.updated_at
            await session.commit()
        return campaign

    async def list_all(self) -> list[Campaign]:
        async with async_session() as session:
            result = await session.execute(
                select(CampaignRow).order_by(CampaignRow.created_at.desc())
            )
            rows = result.scalars().all()
            return [Campaign.model_validate_json(r.data) for r in rows]

    async def delete(self, campaign_id: str) -> bool:
        async with async_session() as session:
            result = await session.execute(
                sa_delete(CampaignRow).where(CampaignRow.id == campaign_id)
            )
            await session.commit()
            return result.rowcount > 0


# Module-level singleton
_store: CampaignStore | None = None


def get_campaign_store() -> CampaignStore:
    global _store
    if _store is None:
        _store = CampaignStore()
    return _store
