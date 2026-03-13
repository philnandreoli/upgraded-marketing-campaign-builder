"""
Tests for the EventStore service.

Unit tests use an in-memory EventStore backed by an in-memory list — no
database connection is required.  Integration tests are skipped when
DATABASE_URL is absent.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest

from backend.models.events import CampaignEventLog


# ---------------------------------------------------------------------------
# In-memory EventStore for unit tests
# ---------------------------------------------------------------------------

class InMemoryEventStore:
    """Dict-backed event store for unit tests — no database required."""

    def __init__(self):
        self._events: list[dict] = []

    async def save_event(
        self,
        campaign_id: str,
        event_type: str,
        payload: dict,
        stage: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        self._events.append(
            {
                "id": event_id,
                "campaign_id": campaign_id,
                "event_type": event_type,
                "stage": stage,
                "payload": payload,
                "owner_id": owner_id,
                "created_at": datetime.now(timezone.utc),
            }
        )
        return event_id

    async def get_events(
        self,
        campaign_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CampaignEventLog]:
        matching = [e for e in self._events if e["campaign_id"] == campaign_id]
        sliced = matching[offset : offset + limit]
        return [
            CampaignEventLog(
                id=e["id"],
                campaign_id=e["campaign_id"],
                event_type=e["event_type"],
                stage=e["stage"],
                payload=e["payload"],
                owner_id=e["owner_id"],
                created_at=e["created_at"],
            )
            for e in sliced
        ]


# ---------------------------------------------------------------------------
# Unit tests — in-memory store
# ---------------------------------------------------------------------------


class TestInMemoryEventStore:
    """Tests against the in-memory EventStore (no DB required)."""

    @pytest.fixture
    def store(self):
        return InMemoryEventStore()

    async def test_save_returns_string_id(self, store):
        event_id = await store.save_event(
            campaign_id="camp-1",
            event_type="pipeline_started",
            payload={"campaign_id": "camp-1"},
        )
        assert isinstance(event_id, str)
        assert len(event_id) > 0

    async def test_get_events_empty_when_none_saved(self, store):
        events = await store.get_events("camp-1")
        assert events == []

    async def test_save_and_retrieve(self, store):
        await store.save_event(
            campaign_id="camp-1",
            event_type="pipeline_started",
            payload={"campaign_id": "camp-1"},
        )
        events = await store.get_events("camp-1")
        assert len(events) == 1
        assert events[0].event_type == "pipeline_started"
        assert events[0].campaign_id == "camp-1"

    async def test_stage_and_owner_id_stored(self, store):
        await store.save_event(
            campaign_id="camp-1",
            event_type="stage_completed",
            payload={"stage": "strategy"},
            stage="strategy",
            owner_id="user-1",
        )
        events = await store.get_events("camp-1")
        assert len(events) == 1
        assert events[0].stage == "strategy"
        assert events[0].owner_id == "user-1"

    async def test_get_events_only_matches_campaign_id(self, store):
        await store.save_event("camp-A", "pipeline_started", {"campaign_id": "camp-A"})
        await store.save_event("camp-B", "pipeline_started", {"campaign_id": "camp-B"})
        events = await store.get_events("camp-A")
        assert len(events) == 1
        assert events[0].campaign_id == "camp-A"

    async def test_multiple_events_returned_in_order(self, store):
        await store.save_event("camp-1", "pipeline_started", {})
        await store.save_event("camp-1", "stage_completed", {"stage": "strategy"})
        await store.save_event("camp-1", "stage_completed", {"stage": "content"})
        events = await store.get_events("camp-1")
        assert len(events) == 3
        assert events[0].event_type == "pipeline_started"
        assert events[1].event_type == "stage_completed"
        assert events[2].event_type == "stage_completed"

    async def test_limit_pagination(self, store):
        for i in range(5):
            await store.save_event("camp-1", f"event_{i}", {})
        events = await store.get_events("camp-1", limit=3)
        assert len(events) == 3

    async def test_offset_pagination(self, store):
        for i in range(5):
            await store.save_event("camp-1", f"event_{i}", {})
        events = await store.get_events("camp-1", limit=10, offset=3)
        assert len(events) == 2

    async def test_payload_stored_correctly(self, store):
        payload = {"campaign_id": "camp-1", "extra": "data", "count": 42}
        await store.save_event("camp-1", "pipeline_started", payload)
        events = await store.get_events("camp-1")
        assert events[0].payload == payload

    async def test_event_log_model_fields(self, store):
        await store.save_event("camp-1", "pipeline_started", {"campaign_id": "camp-1"})
        event = (await store.get_events("camp-1"))[0]
        assert isinstance(event, CampaignEventLog)
        assert isinstance(event.id, str)
        assert isinstance(event.created_at, datetime)


# ---------------------------------------------------------------------------
# Tests for the real EventStore via patching
# ---------------------------------------------------------------------------


class TestEventStoreModule:
    """Tests for the real EventStore class with DB calls mocked."""

    def _make_row(self, **kwargs):
        """Build a minimal mock CampaignEventRow."""
        from unittest.mock import MagicMock

        row = MagicMock()
        row.id = kwargs.get("id", str(uuid.uuid4()))
        row.campaign_id = kwargs.get("campaign_id", "camp-1")
        row.event_type = kwargs.get("event_type", "pipeline_started")
        row.stage = kwargs.get("stage", None)
        row.payload = json.dumps(kwargs.get("payload", {}))
        row.owner_id = kwargs.get("owner_id", None)
        row.created_at = kwargs.get("created_at", datetime(2026, 1, 1, 0, 0, 0))
        return row

    async def test_save_event_inserts_row(self):
        from backend.infrastructure.event_store import EventStore

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.add = AsyncMock()
        mock_session.commit = AsyncMock()

        store = EventStore()
        with patch(
            "backend.infrastructure.event_store.async_session",
            return_value=mock_session,
        ):
            event_id = await store.save_event(
                campaign_id="camp-1",
                event_type="pipeline_started",
                payload={"campaign_id": "camp-1"},
            )

        assert isinstance(event_id, str)
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    async def test_get_events_returns_campaign_event_logs(self):
        from backend.infrastructure.event_store import EventStore
        from unittest.mock import MagicMock

        row = self._make_row(event_type="stage_completed", stage="strategy")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [row]

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=mock_result)

        store = EventStore()
        with patch(
            "backend.infrastructure.event_store.async_session",
            return_value=mock_session,
        ):
            events = await store.get_events("camp-1")

        assert len(events) == 1
        assert isinstance(events[0], CampaignEventLog)
        assert events[0].event_type == "stage_completed"
        assert events[0].stage == "strategy"

    async def test_get_events_returns_empty_list_when_no_rows(self):
        from backend.infrastructure.event_store import EventStore
        from unittest.mock import MagicMock

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=mock_result)

        store = EventStore()
        with patch(
            "backend.infrastructure.event_store.async_session",
            return_value=mock_session,
        ):
            events = await store.get_events("camp-1")

        assert events == []


# ---------------------------------------------------------------------------
# Integration tests — real PostgreSQL store (skipped when DB unavailable)
# ---------------------------------------------------------------------------

import os  # noqa: E402

_skip_no_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping PostgreSQL integration tests",
)


@_skip_no_db
class TestEventStoreIntegration:
    """Integration tests against the real PostgreSQL-backed store."""

    @pytest.fixture
    def es(self):
        from backend.infrastructure.event_store import EventStore
        return EventStore()

    @pytest.fixture
    async def persisted_campaign(self):
        """Insert a campaign row so FK constraints are satisfied."""
        from backend.infrastructure.database import async_session, CampaignRow

        now = datetime.now(timezone.utc)
        row = CampaignRow(
            id="event-integ-camp-001",
            owner_id=None,
            status="draft",
            data='{"id": "event-integ-camp-001", "status": "draft"}',
            created_at=now,
            updated_at=now,
        )
        async with async_session() as session:
            # Clean up any existing row from a prior run
            existing = await session.get(CampaignRow, "event-integ-camp-001")
            if existing is None:
                session.add(row)
                await session.commit()
        return "event-integ-camp-001"

    async def test_save_and_retrieve(self, es, persisted_campaign):
        campaign_id = persisted_campaign
        event_id = await es.save_event(
            campaign_id=campaign_id,
            event_type="pipeline_started",
            payload={"campaign_id": campaign_id},
        )
        assert isinstance(event_id, str)

        events = await es.get_events(campaign_id)
        ids = [e.id for e in events]
        assert event_id in ids

        matching = next(e for e in events if e.id == event_id)
        assert matching.event_type == "pipeline_started"

    async def test_stage_and_owner_persisted(self, es, persisted_campaign):
        campaign_id = persisted_campaign
        event_id = await es.save_event(
            campaign_id=campaign_id,
            event_type="stage_completed",
            payload={"stage": "content"},
            stage="content",
            owner_id="integration-user-1",
        )
        events = await es.get_events(campaign_id)
        matching = next((e for e in events if e.id == event_id), None)
        assert matching is not None
        assert matching.stage == "content"
        assert matching.owner_id == "integration-user-1"

    async def test_get_events_pagination(self, es, persisted_campaign):
        campaign_id = persisted_campaign
        for i in range(5):
            await es.save_event(campaign_id, f"test_event_{i}", {})

        first_page = await es.get_events(campaign_id, limit=3, offset=0)
        second_page = await es.get_events(campaign_id, limit=3, offset=3)
        assert len(first_page) <= 3
        all_events = await es.get_events(campaign_id, limit=200)
        assert len(all_events) >= 5
