"""
Unit tests for event_subscriber.py

Tests cover:
- EventSubscriber receives a notification and calls ws_manager.broadcast()
- EventSubscriber resolves overflow_id references via the database
- EventSubscriber skips non-JSON payloads with a warning
- EventSubscriber reconnects with exponential back-off after connection loss
- EventSubscriber stops cleanly when stop() is called
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.event_subscriber import EventSubscriber


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_subscriber(channel: str = "workflow_events") -> tuple[EventSubscriber, MagicMock]:
    ws_manager = MagicMock()
    ws_manager.broadcast = AsyncMock()
    subscriber = EventSubscriber(
        dsn="postgresql://user:pass@localhost/db",
        ws_manager=ws_manager,
        channel_name=channel,
    )
    return subscriber, ws_manager


# ---------------------------------------------------------------------------
# _handle_notification — core dispatch logic
# ---------------------------------------------------------------------------


class TestHandleNotification:
    async def test_broadcasts_parsed_payload(self):
        """A valid JSON NOTIFY payload must be forwarded to ws_manager.broadcast()."""
        subscriber, ws = _make_subscriber()
        payload = json.dumps({"event": "stage_started", "campaign_id": "c-1"})

        await subscriber._handle_notification(payload)

        ws.broadcast.assert_awaited_once_with(
            {"event": "stage_started", "campaign_id": "c-1"}
        )

    async def test_skips_non_json_payload(self, caplog):
        """Non-JSON payloads must be skipped with a warning and not raise."""
        import logging

        subscriber, ws = _make_subscriber()

        with caplog.at_level(logging.WARNING, logger="backend.services.event_subscriber"):
            await subscriber._handle_notification("not valid json {{")

        ws.broadcast.assert_not_awaited()
        assert "non-JSON" in caplog.text

    async def test_broadcast_exception_is_caught(self, caplog):
        """Exceptions from ws_manager.broadcast() must be caught and logged."""
        import logging

        subscriber, ws = _make_subscriber()
        ws.broadcast = AsyncMock(side_effect=RuntimeError("ws error"))
        payload = json.dumps({"event": "x", "campaign_id": "c-1"})

        with caplog.at_level(logging.ERROR, logger="backend.services.event_subscriber"):
            await subscriber._handle_notification(payload)

        assert "ws_manager.broadcast" in caplog.text

    async def test_resolves_overflow_id(self):
        """Payloads with overflow_id must resolve via _resolve_overflow."""
        subscriber, ws = _make_subscriber()
        full_payload = {"event": "big_event", "campaign_id": "c-big", "data": "x" * 100}
        subscriber._resolve_overflow = AsyncMock(return_value=full_payload)

        overflow_msg = json.dumps({"overflow_id": "some-uuid"})
        await subscriber._handle_notification(overflow_msg)

        subscriber._resolve_overflow.assert_awaited_once_with("some-uuid")
        ws.broadcast.assert_awaited_once_with(full_payload)

    async def test_overflow_resolution_failure_skips_broadcast(self):
        """If _resolve_overflow returns None, broadcast must not be called."""
        subscriber, ws = _make_subscriber()
        subscriber._resolve_overflow = AsyncMock(return_value=None)

        overflow_msg = json.dumps({"overflow_id": "missing-uuid"})
        await subscriber._handle_notification(overflow_msg)

        ws.broadcast.assert_not_awaited()


# ---------------------------------------------------------------------------
# _resolve_overflow — database lookup
# ---------------------------------------------------------------------------


class TestResolveOverflow:
    async def test_returns_parsed_payload_on_success(self):
        """_resolve_overflow must return the parsed JSON from event_overflow."""
        subscriber, _ = _make_subscriber()
        full = {"event": "big_event", "campaign_id": "c-x"}

        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, i: json.dumps(full)

        mock_result = MagicMock()
        mock_result.fetchone = MagicMock(return_value=mock_row)

        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(return_value=mock_result)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        mock_engine = MagicMock()
        mock_engine.connect = MagicMock(return_value=mock_conn)

        with patch("backend.services.database.engine", mock_engine):
            result = await subscriber._resolve_overflow("some-uuid")

        assert result == full

    async def test_returns_none_when_row_not_found(self, caplog):
        """_resolve_overflow must return None when the overflow row is missing."""
        import logging

        subscriber, _ = _make_subscriber()

        mock_result = MagicMock()
        mock_result.fetchone = MagicMock(return_value=None)

        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(return_value=mock_result)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        mock_engine = MagicMock()
        mock_engine.connect = MagicMock(return_value=mock_conn)

        with (
            patch("backend.services.database.engine", mock_engine),
            caplog.at_level(logging.WARNING, logger="backend.services.event_subscriber"),
        ):
            result = await subscriber._resolve_overflow("missing-uuid")

        assert result is None
        assert "missing-uuid" in caplog.text

    async def test_returns_none_on_db_exception(self, caplog):
        """_resolve_overflow must return None (not raise) on database errors."""
        import logging

        subscriber, _ = _make_subscriber()

        mock_engine = MagicMock()
        mock_engine.connect = MagicMock(side_effect=RuntimeError("db down"))

        with (
            patch("backend.services.database.engine", mock_engine),
            caplog.at_level(logging.ERROR, logger="backend.services.event_subscriber"),
        ):
            result = await subscriber._resolve_overflow("err-uuid")

        assert result is None


# ---------------------------------------------------------------------------
# start() / stop() lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_start_schedules_background_task(self):
        """start() must create a background task."""
        subscriber, _ = _make_subscriber()

        async def _fake_listen_loop():
            await asyncio.sleep(60)

        with patch.object(subscriber, "_listen_loop", side_effect=_fake_listen_loop):
            subscriber.start()
            await asyncio.sleep(0)  # let the task start

            assert subscriber._task is not None
            assert not subscriber._task.done()

            await subscriber.stop()

    async def test_stop_cancels_the_task(self):
        """stop() must cancel the running subscriber task."""
        subscriber, _ = _make_subscriber()

        task_started = asyncio.Event()
        task_cancelled = asyncio.Event()

        async def _hanging():
            task_started.set()
            try:
                await asyncio.sleep(999)
            except asyncio.CancelledError:
                task_cancelled.set()
                raise

        with patch.object(subscriber, "_listen_loop", side_effect=_hanging):
            subscriber.start()
            await task_started.wait()
            await subscriber.stop()

        assert task_cancelled.is_set()

    async def test_stop_without_start_does_not_raise(self):
        """stop() must be safe to call before start()."""
        subscriber, _ = _make_subscriber()
        await subscriber.stop()  # must not raise


# ---------------------------------------------------------------------------
# Reconnect logic
# ---------------------------------------------------------------------------


class TestReconnect:
    async def test_reconnects_after_connection_error(self):
        """The subscriber must attempt to reconnect after a connection failure."""
        subscriber, _ = _make_subscriber()

        call_count = 0

        async def _failing_then_stop():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("simulated disconnect")
            # Second call: set stop and return cleanly
            subscriber._stop_event.set()

        with (
            patch.object(subscriber, "_listen_loop", side_effect=_failing_then_stop),
            patch(
                "backend.services.event_subscriber._INITIAL_BACKOFF", 0.01
            ),
        ):
            subscriber.start()
            # Allow enough time for the reconnect cycle
            await asyncio.wait_for(subscriber._task, timeout=3.0)

        assert call_count == 2

    async def test_stop_during_backoff_exits_cleanly(self):
        """Calling stop() while the subscriber is waiting to reconnect must exit."""
        subscriber, _ = _make_subscriber()

        called = asyncio.Event()

        async def _always_fail():
            called.set()
            raise ConnectionError("fail")

        with (
            patch.object(subscriber, "_listen_loop", side_effect=_always_fail),
            patch("backend.services.event_subscriber._INITIAL_BACKOFF", 60.0),
        ):
            subscriber.start()
            await called.wait()
            # Stop while still in back-off
            await subscriber.stop()

        assert subscriber._task.done()
