"""
Event subscriber for cross-process event delivery via PostgreSQL LISTEN/NOTIFY.

``EventSubscriber`` opens a dedicated ``asyncpg`` connection to the PostgreSQL
database and issues ``LISTEN <channel>``.  When a notification arrives it is
forwarded to all connected WebSocket clients via ``ws_manager.broadcast()``.

Overflow resolution
-------------------
If the NOTIFY payload is the JSON object ``{"overflow_id": "<uuid>"}``, the
subscriber fetches the full payload from the ``event_overflow`` table before
broadcasting.

Connection resilience
---------------------
The subscriber reconnects automatically after a lost connection using
exponential back-off (capped at 60 s) so that a transient database restart
does not permanently break real-time updates.

Lifecycle
---------
``EventSubscriber`` is started during ``on_startup`` in ``backend/main.py``
only when ``WORKFLOW_EXECUTOR != "in_process"``.  When in-process mode is
active, events flow directly without Postgres involvement.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Maximum back-off seconds between reconnect attempts
_MAX_BACKOFF = 60.0
# Starting back-off delay
_INITIAL_BACKOFF = 1.0


class EventSubscriber:
    """Subscribe to PostgreSQL NOTIFY events and forward them to WebSocket clients.

    Parameters
    ----------
    dsn:
        asyncpg-compatible connection string, e.g.
        ``postgresql://user:pass@host:5432/db``.
    ws_manager:
        The ``ConnectionManager`` singleton from ``backend.api.websocket``.
    channel_name:
        The NOTIFY channel to subscribe to (default ``"workflow_events"``).
    password:
        Optional coroutine function that returns an access token string.
        When provided (azure mode), it is passed to ``asyncpg.connect()`` as
        the ``password`` argument so that a fresh Entra token is acquired for
        each new connection.  Pass ``None`` (default) for password-in-DSN
        (local mode).
    """

    def __init__(
        self,
        dsn: str,
        ws_manager: Any,
        channel_name: str = "workflow_events",
        password: "Callable[[], Coroutine[Any, Any, str]] | None" = None,
    ) -> None:
        self._dsn = dsn
        self._ws_manager = ws_manager
        self._channel_name = channel_name
        self._password = password
        self._stop_event: asyncio.Event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Schedule the subscriber loop as a background asyncio task."""
        self._stop_event.clear()
        self._task = asyncio.ensure_future(self._run())
        logger.info(
            "EventSubscriber started (channel=%s)", self._channel_name
        )

    async def stop(self) -> None:
        """Signal the subscriber to stop and wait for the task to finish."""
        self._stop_event.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("EventSubscriber stopped")

    # ------------------------------------------------------------------
    # Internal: reconnect loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Outer loop: connect, listen, reconnect on failure."""
        backoff = _INITIAL_BACKOFF
        while not self._stop_event.is_set():
            try:
                await self._listen_loop()
                # _listen_loop returned cleanly (stop requested)
                break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.warning(
                    "EventSubscriber connection lost (%s); reconnecting in %.1fs",
                    exc,
                    backoff,
                )
                try:
                    await asyncio.wait_for(
                        asyncio.shield(self._stop_event.wait()),
                        timeout=backoff,
                    )
                    # stop_event was set during the back-off
                    break
                except asyncio.TimeoutError:
                    pass

                backoff = min(backoff * 2, _MAX_BACKOFF)

    async def _listen_loop(self) -> None:
        """Connect to Postgres, LISTEN, and dispatch notifications."""
        import asyncpg  # noqa: PLC0415

        connect_kwargs: dict[str, Any] = {}
        if self._password is not None:
            connect_kwargs["password"] = self._password
            connect_kwargs["ssl"] = "require"

        conn: asyncpg.Connection = await asyncpg.connect(dsn=self._dsn, **connect_kwargs)
        logger.info(
            "EventSubscriber connected, listening on channel=%s",
            self._channel_name,
        )
        try:
            # Reset back-off on successful connection (done in the caller's loop)
            await conn.add_listener(self._channel_name, self._on_notification)

            # Block until a stop is requested or the connection drops
            await self._stop_event.wait()
        finally:
            try:
                await conn.remove_listener(self._channel_name, self._on_notification)
            except Exception:
                pass
            try:
                await conn.close()
            except Exception:
                pass

    def _on_notification(
        self,
        connection: Any,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        """Sync callback invoked by asyncpg for each NOTIFY."""
        asyncio.ensure_future(self._handle_notification(payload))

    async def _handle_notification(self, raw_payload: str) -> None:
        """Parse the payload and broadcast to WebSocket clients."""
        try:
            data = json.loads(raw_payload)
        except json.JSONDecodeError:
            logger.warning(
                "EventSubscriber: received non-JSON NOTIFY payload; skipping"
            )
            return

        # Resolve overflow reference if present
        if "overflow_id" in data:
            data = await self._resolve_overflow(data["overflow_id"])
            if data is None:
                return

        try:
            await self._ws_manager.broadcast(data)
        except Exception:
            logger.exception("EventSubscriber: ws_manager.broadcast() failed")

    async def _resolve_overflow(self, overflow_id: str) -> dict[str, Any] | None:
        """Fetch the full payload from event_overflow and return it as a dict."""
        import sqlalchemy  # noqa: PLC0415
        from backend.infrastructure.database import engine  # noqa: PLC0415

        try:
            async with engine.connect() as conn:
                row = await conn.execute(
                    sqlalchemy.text(
                        "SELECT payload FROM event_overflow WHERE id = :id"
                    ),
                    {"id": overflow_id},
                )
                result = row.fetchone()

            if result is None:
                logger.warning(
                    "EventSubscriber: overflow_id %s not found in event_overflow",
                    overflow_id,
                )
                return None

            return json.loads(result[0])

        except Exception:
            logger.exception(
                "EventSubscriber: failed to resolve overflow_id=%s", overflow_id
            )
            return None
