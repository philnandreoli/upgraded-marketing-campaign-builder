"""
PostgreSQL-backed campaign event store.

Persists pipeline events emitted by the CoordinatorAgent so that a full
audit trail is available even after the browser session ends.  Events are
written here by the worker's ``_on_event`` callback and read back by the
``GET /campaigns/{id}/events`` API endpoint.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from backend.infrastructure.database import CampaignEventRow, async_session
from backend.models.events import CampaignEventLog


class EventStore:
    """Repository for ``CampaignEventRow`` records backed by PostgreSQL."""

    async def save_event(
        self,
        campaign_id: str,
        event_type: str,
        payload: dict,
        stage: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> str:
        """Persist a single pipeline event and return its UUID string ID."""
        event_id = str(uuid.uuid4())
        row = CampaignEventRow(
            id=event_id,
            campaign_id=campaign_id,
            event_type=event_type,
            stage=stage,
            payload=json.dumps(payload, default=str),
            owner_id=owner_id,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
        return event_id

    async def get_events(
        self,
        campaign_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CampaignEventLog]:
        """Retrieve historical events for a campaign, ordered by creation time.

        Parameters
        ----------
        campaign_id:
            The campaign whose events to retrieve.
        limit:
            Maximum number of events to return (default 100).
        offset:
            Number of events to skip for pagination (default 0).
        """
        async with async_session() as session:
            stmt = (
                select(CampaignEventRow)
                .where(CampaignEventRow.campaign_id == campaign_id)
                .order_by(CampaignEventRow.created_at)
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [
            CampaignEventLog(
                id=row.id,
                campaign_id=row.campaign_id,
                event_type=row.event_type,
                stage=row.stage,
                payload=json.loads(row.payload),
                owner_id=row.owner_id,
                created_at=row.created_at,
            )
            for row in rows
        ]


# Module-level singleton
_event_store: EventStore | None = None


def get_event_store() -> EventStore:
    global _event_store
    if _event_store is None:
        _event_store = EventStore()
    return _event_store
