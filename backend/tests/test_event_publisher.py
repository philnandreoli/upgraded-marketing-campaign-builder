"""
Unit tests for event_publisher.py

Tests cover:
- InProcessEventPublisher: delegates to ws_manager.broadcast()
- PostgresEventPublisher: sends NOTIFY with correct channel and payload
- PostgresEventPublisher: stores overflow payload when payload exceeds 8000 bytes
- PostgresEventPublisher: sends overflow reference when payload is too large
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from backend.services.event_publisher import (
    EventPublisher,
    InProcessEventPublisher,
    PostgresEventPublisher,
    _NOTIFY_MAX_BYTES,
)


# ---------------------------------------------------------------------------
# InProcessEventPublisher
# ---------------------------------------------------------------------------


class TestInProcessEventPublisher:
    async def test_publish_calls_broadcast_with_event(self):
        """publish() must call ws_manager.broadcast() with event merged into data."""
        mock_ws = MagicMock()
        mock_ws.broadcast = AsyncMock()
        publisher = InProcessEventPublisher(mock_ws)

        await publisher.publish("stage_started", {"campaign_id": "c-1", "stage": "research"})

        mock_ws.broadcast.assert_awaited_once_with(
            {"event": "stage_started", "campaign_id": "c-1", "stage": "research"}
        )

    async def test_publish_event_key_is_included(self):
        """The 'event' key must be present in the broadcast message."""
        mock_ws = MagicMock()
        mock_ws.broadcast = AsyncMock()
        publisher = InProcessEventPublisher(mock_ws)

        await publisher.publish("pipeline_completed", {"campaign_id": "c-2"})

        broadcasted = mock_ws.broadcast.call_args[0][0]
        assert broadcasted["event"] == "pipeline_completed"
        assert broadcasted["campaign_id"] == "c-2"

    async def test_close_is_noop(self):
        """close() must not raise and has no side-effects."""
        publisher = InProcessEventPublisher(MagicMock())
        await publisher.close()  # must not raise

    def test_satisfies_protocol(self):
        """InProcessEventPublisher must satisfy the EventPublisher Protocol."""
        publisher = InProcessEventPublisher(MagicMock())
        assert isinstance(publisher, EventPublisher)


# ---------------------------------------------------------------------------
# PostgresEventPublisher — normal payloads
# ---------------------------------------------------------------------------


def _make_engine():
    """Return a mock async SQLAlchemy engine with context manager support."""
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.commit = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    engine = MagicMock()
    engine.connect = MagicMock(return_value=conn)
    return engine, conn


class TestPostgresEventPublisher:
    async def test_publish_executes_pg_notify(self):
        """publish() must execute SELECT pg_notify on the correct channel."""
        import sqlalchemy

        engine, conn = _make_engine()
        publisher = PostgresEventPublisher(engine, channel_name="test_channel")

        await publisher.publish("stage_started", {"campaign_id": "c-1"})

        conn.execute.assert_awaited_once()
        args = conn.execute.call_args
        # First positional arg is a sqlalchemy.text() object
        stmt = args[0][0]
        params = args[0][1]
        assert "pg_notify" in str(stmt)
        assert params["channel"] == "test_channel"

    async def test_publish_payload_contains_event_and_data(self):
        """The NOTIFY payload must be a JSON string with 'event' and data keys."""
        engine, conn = _make_engine()
        publisher = PostgresEventPublisher(engine, channel_name="wf")

        await publisher.publish("approval_requested", {"campaign_id": "c-99", "piece": 0})

        params = conn.execute.call_args[0][1]
        payload = json.loads(params["payload"])
        assert payload["event"] == "approval_requested"
        assert payload["campaign_id"] == "c-99"
        assert payload["piece"] == 0

    async def test_publish_commits_after_execute(self):
        """publish() must commit the connection after executing pg_notify."""
        engine, conn = _make_engine()
        publisher = PostgresEventPublisher(engine)

        await publisher.publish("test_event", {"campaign_id": "c-1"})

        conn.commit.assert_awaited_once()

    async def test_close_is_noop(self):
        """close() must not raise and has no side-effects."""
        engine, _ = _make_engine()
        publisher = PostgresEventPublisher(engine)
        await publisher.close()  # must not raise

    def test_satisfies_protocol(self):
        """PostgresEventPublisher must satisfy the EventPublisher Protocol."""
        publisher = PostgresEventPublisher(MagicMock())
        assert isinstance(publisher, EventPublisher)

    async def test_default_channel_name(self):
        """Default channel name must be 'workflow_events'."""
        engine, conn = _make_engine()
        publisher = PostgresEventPublisher(engine)

        await publisher.publish("e", {})

        params = conn.execute.call_args[0][1]
        assert params["channel"] == "workflow_events"


# ---------------------------------------------------------------------------
# PostgresEventPublisher — overflow handling
# ---------------------------------------------------------------------------


class TestPostgresEventPublisherOverflow:
    def _make_large_payload(self) -> dict:
        """Return a dict whose JSON serialisation exceeds _NOTIFY_MAX_BYTES."""
        return {"campaign_id": "c-x", "large_field": "x" * (_NOTIFY_MAX_BYTES + 100)}

    async def test_oversized_payload_writes_to_overflow_table(self):
        """Payloads > 8000 bytes must be written to event_overflow."""
        engine = MagicMock()

        # begin() context manager (for INSERT)
        begin_conn = MagicMock()
        begin_conn.execute = AsyncMock()
        begin_conn.__aenter__ = AsyncMock(return_value=begin_conn)
        begin_conn.__aexit__ = AsyncMock(return_value=False)
        engine.begin = MagicMock(return_value=begin_conn)

        # connect() context manager (for pg_notify)
        notify_conn = MagicMock()
        notify_conn.execute = AsyncMock()
        notify_conn.commit = AsyncMock()
        notify_conn.__aenter__ = AsyncMock(return_value=notify_conn)
        notify_conn.__aexit__ = AsyncMock(return_value=False)
        engine.connect = MagicMock(return_value=notify_conn)

        publisher = PostgresEventPublisher(engine)
        data = self._make_large_payload()

        await publisher.publish("big_event", data)

        # The INSERT into event_overflow must have been executed
        begin_conn.execute.assert_awaited_once()
        insert_params = begin_conn.execute.call_args[0][1]
        assert insert_params["channel"] == "workflow_events"
        # The stored payload must be the full JSON
        stored = json.loads(insert_params["payload"])
        assert stored["event"] == "big_event"
        assert stored["large_field"] == data["large_field"]

    async def test_oversized_payload_notifies_with_overflow_reference(self):
        """NOTIFY payload must be a compact overflow_id reference for large events."""
        engine = MagicMock()

        begin_conn = MagicMock()
        begin_conn.execute = AsyncMock()
        begin_conn.__aenter__ = AsyncMock(return_value=begin_conn)
        begin_conn.__aexit__ = AsyncMock(return_value=False)
        engine.begin = MagicMock(return_value=begin_conn)

        notify_conn = MagicMock()
        notify_conn.execute = AsyncMock()
        notify_conn.commit = AsyncMock()
        notify_conn.__aenter__ = AsyncMock(return_value=notify_conn)
        notify_conn.__aexit__ = AsyncMock(return_value=False)
        engine.connect = MagicMock(return_value=notify_conn)

        publisher = PostgresEventPublisher(engine)
        data = self._make_large_payload()

        await publisher.publish("big_event", data)

        # The NOTIFY payload must be a small {"overflow_id": "..."} JSON
        notify_params = notify_conn.execute.call_args[0][1]
        notify_payload = json.loads(notify_params["payload"])
        assert "overflow_id" in notify_payload
        assert len(notify_params["payload"].encode()) < _NOTIFY_MAX_BYTES

    async def test_normal_payload_does_not_use_overflow_table(self):
        """Small payloads must not touch the event_overflow table."""
        engine, conn = _make_engine()
        engine.begin = MagicMock()  # Should not be called

        publisher = PostgresEventPublisher(engine)
        await publisher.publish("small_event", {"campaign_id": "c-1"})

        engine.begin.assert_not_called()
