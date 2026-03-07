"""
Tests for WorkflowSignalStore.

Unit tests use the InMemoryWorkflowSignalStore from conftest (no database
required).  Integration tests are skipped when DATABASE_URL is absent.
"""

from __future__ import annotations

import asyncio
import pytest

from backend.services.workflow_signal_store import SignalType


# ---------------------------------------------------------------------------
# Unit tests — in-memory store (provided via conftest autouse fixture)
# ---------------------------------------------------------------------------

class TestSignalType:
    def test_constant_values(self):
        assert SignalType.CLARIFICATION_RESPONSE == "clarification_response"
        assert SignalType.CONTENT_APPROVAL == "content_approval"


class TestInMemoryWorkflowSignalStore:
    """Tests against the InMemoryWorkflowSignalStore injected by conftest."""

    async def test_write_returns_string_id(self, _in_memory_signal_store):
        signal_id = await _in_memory_signal_store.write_signal(
            "camp-1", SignalType.CLARIFICATION_RESPONSE, {"answers": {"q1": "a1"}}
        )
        assert isinstance(signal_id, str)
        assert len(signal_id) > 0

    async def test_poll_returns_none_when_empty(self, _in_memory_signal_store):
        result = await _in_memory_signal_store.poll_signal(
            "camp-1", SignalType.CLARIFICATION_RESPONSE
        )
        assert result is None

    async def test_poll_returns_signal_after_write(self, _in_memory_signal_store):
        payload = {"answers": {"q1": "B2B"}}
        await _in_memory_signal_store.write_signal(
            "camp-1", SignalType.CLARIFICATION_RESPONSE, payload
        )
        result = await _in_memory_signal_store.poll_signal(
            "camp-1", SignalType.CLARIFICATION_RESPONSE
        )
        assert result is not None
        assert result["payload"] == payload

    async def test_poll_only_matches_campaign_id(self, _in_memory_signal_store):
        await _in_memory_signal_store.write_signal(
            "camp-A", SignalType.CLARIFICATION_RESPONSE, {"x": 1}
        )
        result = await _in_memory_signal_store.poll_signal(
            "camp-B", SignalType.CLARIFICATION_RESPONSE
        )
        assert result is None

    async def test_poll_only_matches_signal_type(self, _in_memory_signal_store):
        await _in_memory_signal_store.write_signal(
            "camp-1", SignalType.CLARIFICATION_RESPONSE, {"x": 1}
        )
        result = await _in_memory_signal_store.poll_signal(
            "camp-1", SignalType.CONTENT_APPROVAL
        )
        assert result is None

    async def test_consume_makes_signal_invisible_to_poll(self, _in_memory_signal_store):
        signal_id = await _in_memory_signal_store.write_signal(
            "camp-1", SignalType.CLARIFICATION_RESPONSE, {"answers": {}}
        )
        await _in_memory_signal_store.consume_signal(signal_id)

        result = await _in_memory_signal_store.poll_signal(
            "camp-1", SignalType.CLARIFICATION_RESPONSE
        )
        assert result is None

    async def test_poll_returns_oldest_unconsumed(self, _in_memory_signal_store):
        payload_a = {"order": "first"}
        payload_b = {"order": "second"}
        await _in_memory_signal_store.write_signal(
            "camp-1", SignalType.CONTENT_APPROVAL, payload_a
        )
        await _in_memory_signal_store.write_signal(
            "camp-1", SignalType.CONTENT_APPROVAL, payload_b
        )
        result = await _in_memory_signal_store.poll_signal(
            "camp-1", SignalType.CONTENT_APPROVAL
        )
        assert result is not None
        assert result["payload"]["order"] == "first"

    async def test_write_multiple_campaigns_independent(self, _in_memory_signal_store):
        await _in_memory_signal_store.write_signal(
            "camp-X", SignalType.CONTENT_APPROVAL, {"x": 1}
        )
        await _in_memory_signal_store.write_signal(
            "camp-Y", SignalType.CONTENT_APPROVAL, {"y": 2}
        )
        x_result = await _in_memory_signal_store.poll_signal("camp-X", SignalType.CONTENT_APPROVAL)
        y_result = await _in_memory_signal_store.poll_signal("camp-Y", SignalType.CONTENT_APPROVAL)
        assert x_result["payload"] == {"x": 1}
        assert y_result["payload"] == {"y": 2}

    async def test_consume_idempotent_for_unknown_id(self, _in_memory_signal_store):
        # Should not raise even if the ID doesn't exist
        await _in_memory_signal_store.consume_signal("nonexistent-id")


# ---------------------------------------------------------------------------
# Integration tests — real PostgreSQL store (skipped when DB unavailable)
# ---------------------------------------------------------------------------

import os  # noqa: E402

_skip_no_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping PostgreSQL integration tests",
)


@_skip_no_db
class TestWorkflowSignalStoreIntegration:
    """Integration tests against the real PostgreSQL-backed store."""

    @pytest.fixture
    def pg_store(self):
        from backend.services.workflow_signal_store import WorkflowSignalStore
        return WorkflowSignalStore()

    @pytest.fixture
    async def persisted_campaign(self):
        """Insert a campaign row so FK constraints are satisfied."""
        from backend.services.database import async_session, CampaignRow
        from datetime import datetime

        now = datetime.utcnow()
        row = CampaignRow(
            id="sig-integ-camp-001",
            owner_id=None,
            status="draft",
            data='{"id": "sig-integ-camp-001", "status": "draft"}',
            created_at=now,
            updated_at=now,
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
        return "sig-integ-camp-001"

    async def test_write_poll_consume_cycle(self, pg_store, persisted_campaign):
        campaign_id = persisted_campaign
        payload = {"answers": {"q1": "enterprise"}}

        signal_id = await pg_store.write_signal(
            campaign_id, SignalType.CLARIFICATION_RESPONSE, payload
        )
        assert isinstance(signal_id, str)

        result = await pg_store.poll_signal(campaign_id, SignalType.CLARIFICATION_RESPONSE)
        assert result is not None
        assert result["id"] == signal_id
        assert result["payload"] == payload

        await pg_store.consume_signal(signal_id)

        after_consume = await pg_store.poll_signal(campaign_id, SignalType.CLARIFICATION_RESPONSE)
        assert after_consume is None

    async def test_poll_returns_none_when_empty(self, pg_store, persisted_campaign):
        result = await pg_store.poll_signal(persisted_campaign, SignalType.CONTENT_APPROVAL)
        assert result is None
