"""API-specific startup and shutdown lifecycle helpers.

Provides factory functions that create the startup and shutdown event handlers
for the FastAPI application.  These are API-only concerns:

- Database initialisation / teardown
- External event subscriber wiring (Postgres LISTEN/NOTIFY → WebSocket relay)

The workflow-engine agent registration is intentionally **not** performed here;
it belongs to the worker/orchestration boundary, not the HTTP API.
"""

from __future__ import annotations

import logging
from typing import Callable

from backend.config import get_settings
from backend.infrastructure.database import close_db, init_db

logger = logging.getLogger(__name__)


def make_startup_handler(app: object) -> Callable[[], None]:
    """Return an async startup handler that stores state on *app*."""

    settings = get_settings()

    async def on_startup() -> None:
        await init_db()

        # Start the cross-process event subscriber only when the pipeline
        # executes in an external worker process.  In in-process mode, events
        # flow directly via InProcessEventPublisher without Postgres
        # LISTEN/NOTIFY.
        if settings.app.workflow_executor != "in_process":
            from backend.api.websocket import manager as ws_manager  # noqa: PLC0415
            from backend.infrastructure.database import DATABASE_URL  # noqa: PLC0415
            from backend.infrastructure.event_subscriber import EventSubscriber  # noqa: PLC0415

            dsn = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
            subscriber = EventSubscriber(
                dsn=dsn,
                ws_manager=ws_manager,
                channel_name=settings.events.channel_name,
            )
            subscriber.start()
            app.state.event_subscriber = subscriber  # type: ignore[union-attr]

    return on_startup


def make_shutdown_handler(app: object) -> Callable[[], None]:
    """Return an async shutdown handler that reads state from *app*."""

    async def on_shutdown() -> None:
        subscriber = getattr(getattr(app, "state", None), "event_subscriber", None)
        if subscriber is not None:
            await subscriber.stop()
        await close_db()

    return on_shutdown
