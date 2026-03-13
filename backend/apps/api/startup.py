"""API-specific startup and shutdown lifecycle helpers.

Provides factory functions that create the startup and shutdown event handlers
for the FastAPI application.  These are API-only concerns:

- Database initialisation / teardown
- External event subscriber wiring (Postgres LISTEN/NOTIFY → WebSocket relay)
- Auto-resume of stuck pipelines (in-process executor only)

The workflow-engine agent registration is intentionally **not** performed here;
it belongs to the worker/orchestration boundary, not the HTTP API.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from backend.config import get_settings
from backend.infrastructure.campaign_store import get_campaign_store
from backend.infrastructure.database import close_db, init_db
from backend.infrastructure.workflow_executor import WorkflowJob, get_executor

logger = logging.getLogger(__name__)

# Campaign statuses that represent an in-flight pipeline interrupted by a restart.
# Terminal statuses (APPROVED, REJECTED, MANUAL_REVIEW_REQUIRED) and DRAFT are
# intentionally excluded — only campaigns actively waiting for input or actively
# executing a stage need to be resumed.
from backend.models.campaign import CampaignStatus

_RESUMABLE_STATUSES = [
    CampaignStatus.CLARIFICATION,
    CampaignStatus.STRATEGY,
    CampaignStatus.CONTENT,
    CampaignStatus.CHANNEL_PLANNING,
    CampaignStatus.ANALYTICS_SETUP,
    CampaignStatus.REVIEW,
    CampaignStatus.CONTENT_REVISION,
    CampaignStatus.CONTENT_APPROVAL,
]

# Seconds to wait after startup before sweeping for stuck campaigns.
# Allows the event loop and DB connection pool to fully initialise.
_AUTO_RESUME_DELAY_SECONDS = 1


def _check_cors_safety(app_env: str, allowed_origins: list[str]) -> None:
    """Refuse to start when wildcard CORS origins are used outside development.

    A wildcard origin combined with ``allow_credentials=True`` opens the API
    to cross-origin data exfiltration (OWASP A01:2021 — Broken Access Control).
    Set ``CORS_ALLOWED_ORIGINS`` to an explicit JSON array before deploying,
    e.g. ``'["https://app.example.com"]'``.
    """
    if app_env != "development" and "*" in allowed_origins:
        logger.critical(
            "CORS_ALLOWED_ORIGINS contains wildcard '*' in non-development "
            "environment (%s). Set explicit origins for production.",
            app_env,
        )
        raise SystemExit(1)


def make_startup_handler(app: object) -> Callable[[], None]:
    """Return an async startup handler that stores state on *app*."""

    settings = get_settings()

    async def on_startup() -> None:
        # CORS safety guard — refuse to start in non-development environments
        # when wildcard origins are still configured.
        _check_cors_safety(settings.app.env, settings.cors.allowed_origins)

        await init_db()

        # Start the cross-process event subscriber only when the pipeline
        # executes in an external worker process.  In in-process mode, events
        # flow directly via InProcessEventPublisher without Postgres
        # LISTEN/NOTIFY.
        if settings.app.workflow_executor != "in_process":
            from backend.api.websocket import manager as ws_manager  # noqa: PLC0415
            from backend.infrastructure.database import (  # noqa: PLC0415
                get_connection_dsn,
                get_connection_password,
            )
            from backend.infrastructure.event_subscriber import EventSubscriber  # noqa: PLC0415

            subscriber = EventSubscriber(
                dsn=get_connection_dsn(),
                ws_manager=ws_manager,
                channel_name=settings.events.channel_name,
                password=get_connection_password(),
            )
            subscriber.start()
            app.state.event_subscriber = subscriber  # type: ignore[union-attr]

        # Start the background task that evicts expired WS tickets.
        from backend.api.websocket import start_ticket_cleanup_task  # noqa: PLC0415
        start_ticket_cleanup_task()

        # Auto-resume stuck pipelines after a server restart.  This only
        # applies to the in-process executor (local dev / single-process
        # deployment) and can be disabled via AUTO_RESUME_ON_STARTUP=false.
        if (
            settings.app.workflow_executor == "in_process"
            and settings.app.auto_resume_on_startup
        ):
            asyncio.ensure_future(_auto_resume_stuck_pipelines())

    return on_startup


async def _auto_resume_stuck_pipelines() -> None:
    """Query for campaigns stuck in interruptible states and dispatch resume jobs.

    A short delay allows the event loop and DB connection pool to fully
    initialise before the query runs.
    """
    await asyncio.sleep(_AUTO_RESUME_DELAY_SECONDS)

    try:
        store = get_campaign_store()
        stuck = await store.list_by_status(_RESUMABLE_STATUSES)
    except Exception:  # noqa: BLE001
        logger.exception("auto-resume: failed to query stuck campaigns")
        return

    if not stuck:
        return

    executor = get_executor()
    for campaign in stuck:
        logger.warning(
            "auto-resume: dispatching resume_pipeline for campaign %s (status=%s)",
            campaign.id,
            campaign.status.value,
        )
        try:
            await executor.dispatch(
                WorkflowJob(campaign_id=campaign.id, action="resume_pipeline")
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "auto-resume: failed to dispatch resume for campaign %s", campaign.id
            )


def make_shutdown_handler(app: object) -> Callable[[], None]:
    """Return an async shutdown handler that reads state from *app*."""

    async def on_shutdown() -> None:
        subscriber = getattr(getattr(app, "state", None), "event_subscriber", None)
        if subscriber is not None:
            await subscriber.stop()
        await close_db()

    return on_shutdown
