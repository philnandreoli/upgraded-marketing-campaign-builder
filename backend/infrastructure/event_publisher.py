"""
Event publisher implementations for cross-process event delivery.

Provides two concrete implementations of the ``EventPublisher`` protocol:

- ``InProcessEventPublisher``: calls ``ws_manager.broadcast()`` directly.
  Used by ``InProcessExecutor`` when the coordinator runs in the same process
  as the API server.

- ``PostgresEventPublisher``: issues a PostgreSQL ``NOTIFY`` so that the API
  process (running ``EventSubscriber``) can forward the event to WebSocket
  clients.  Used by the standalone worker process.

Payload overflow
----------------
PostgreSQL limits NOTIFY payloads to 8 000 bytes.  When a serialised event
exceeds this limit, ``PostgresEventPublisher`` writes the full payload to the
``event_overflow`` table and sends a compact reference message instead::

    {"overflow_id": "<uuid>"}

``EventSubscriber`` detects this sentinel and fetches the full payload from
the database before broadcasting.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# PostgreSQL NOTIFY payload hard limit.  We stay slightly below the true
# 8 190-byte limit to leave room for channel overhead.
_NOTIFY_MAX_BYTES = 8_000


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class EventPublisher(Protocol):
    """Interface for publishing real-time pipeline events."""

    async def publish(self, event: str, data: dict[str, Any]) -> None:
        """Publish *event* with the associated *data* payload."""
        ...

    async def close(self) -> None:
        """Release any resources held by this publisher."""
        ...


# ---------------------------------------------------------------------------
# In-process implementation (same process as the API server)
# ---------------------------------------------------------------------------


class InProcessEventPublisher:
    """Publishes events by calling ``ws_manager.broadcast()`` directly.

    This is the zero-latency path used by ``InProcessExecutor`` when the
    coordinator runs in the same async event loop as the FastAPI app.

    Parameters
    ----------
    ws_manager:
        The ``ConnectionManager`` singleton from ``backend.api.websocket``.
    """

    def __init__(self, ws_manager: Any) -> None:
        self._ws_manager = ws_manager

    async def publish(self, event: str, data: dict[str, Any]) -> None:
        await self._ws_manager.broadcast({"event": event, **data})

    async def close(self) -> None:
        pass  # Nothing to tear down


# ---------------------------------------------------------------------------
# Postgres NOTIFY implementation (cross-process delivery)
# ---------------------------------------------------------------------------


class PostgresEventPublisher:
    """Publishes events via PostgreSQL ``NOTIFY``.

    Uses the SQLAlchemy async engine to execute ``SELECT pg_notify(…)`` so
    that the ``EventSubscriber`` running in the API process can receive the
    notification and forward it to WebSocket clients.

    Large payloads (> 8 000 bytes) are written to the ``event_overflow`` table
    and the NOTIFY message contains only the overflow record's ``id``.

    Parameters
    ----------
    engine:
        The SQLAlchemy ``AsyncEngine`` connected to the same PostgreSQL
        instance.
    channel_name:
        The NOTIFY channel to publish on (default ``"workflow_events"``).
    """

    def __init__(self, engine: Any, channel_name: str = "workflow_events") -> None:
        self._engine = engine
        self._channel_name = channel_name

    async def publish(self, event: str, data: dict[str, Any]) -> None:
        import sqlalchemy  # noqa: PLC0415

        payload = json.dumps({"event": event, **data}, default=str)

        if len(payload.encode()) > _NOTIFY_MAX_BYTES:
            notify_payload = await self._store_overflow(payload)
        else:
            notify_payload = payload

        async with self._engine.connect() as conn:
            await conn.execute(
                sqlalchemy.text("SELECT pg_notify(:channel, :payload)"),
                {"channel": self._channel_name, "payload": notify_payload},
            )
            await conn.commit()

        logger.debug(
            "NOTIFY %s (payload_bytes=%d overflow=%s)",
            self._channel_name,
            len(notify_payload.encode()),
            len(payload.encode()) > _NOTIFY_MAX_BYTES,
        )

    async def _store_overflow(self, payload: str) -> str:
        """Persist *payload* to ``event_overflow`` and return a reference JSON."""
        import sqlalchemy  # noqa: PLC0415

        overflow_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        async with self._engine.begin() as conn:
            await conn.execute(
                sqlalchemy.text(
                    "INSERT INTO event_overflow (id, channel, payload, created_at) "
                    "VALUES (:id, :channel, :payload, :created_at)"
                ),
                {
                    "id": overflow_id,
                    "channel": self._channel_name,
                    "payload": payload,
                    "created_at": now,
                },
            )

        logger.debug(
            "Stored overflow payload (id=%s bytes=%d)",
            overflow_id,
            len(payload.encode()),
        )
        return json.dumps({"overflow_id": overflow_id})

    async def close(self) -> None:
        pass  # The engine lifetime is managed externally
