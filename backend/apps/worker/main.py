"""
Workflow-engine worker process entry point.

Connects to an Azure Service Bus session queue and processes ``WorkflowJob``
messages by dispatching them to the ``CoordinatorAgent`` pipeline.  Intended
to run as a separate deployment unit alongside the FastAPI web process.

Run with::

    python -m backend.apps.worker.main

Or via the compatibility alias::

    python -m backend.worker
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from backend.config import get_settings
from backend.apps.worker.dependencies import build_sb_client, execute_job
from backend.apps.worker.health import HealthServer
from backend.apps.worker.runner import QueueRunner

logger = logging.getLogger(__name__)


class Worker:
    """Orchestrates the queue runner and health server for pipeline job execution.

    Parameters
    ----------
    sb_client:
        Pre-built ``ServiceBusClient`` instance.  When ``None`` (the default),
        a client is created from the configured credentials on ``run()``.
        Provide an explicit client in tests to avoid live Azure connections.
    """

    def __init__(self, *, sb_client: Any = None) -> None:
        settings = get_settings()
        self._sb_settings = settings.service_bus
        self._worker_settings = settings.worker

        self._shutdown_event = asyncio.Event()

        # Service Bus client — injected for testing, otherwise created in run()
        self._sb_client = sb_client
        self._credential: Any = None

        # Runner is created in run(); None before the worker has started.
        self._runner: QueueRunner | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Initialise the Service Bus connection and start processing.

        Returns once graceful shutdown completes.
        """
        if self._sb_client is None:
            credential_holder: list[Any] = []
            self._sb_client = await build_sb_client(
                namespace=self._sb_settings.namespace,
                connection_string=self._sb_settings.connection_string,
                credential_holder=credential_holder,
            )
            self._credential = credential_holder[0] if credential_holder else None

        self._runner = QueueRunner(
            sb_client=self._sb_client,
            queue_name=self._sb_settings.queue_name,
            shutdown_event=self._shutdown_event,
            max_concurrency=self._worker_settings.max_concurrency,
            shutdown_timeout_seconds=self._worker_settings.shutdown_timeout_seconds,
            execute_job=execute_job,
        )

        health_server = HealthServer(
            port=self._worker_settings.health_port,
            shutdown_event=self._shutdown_event,
            get_receiver_active=lambda: self._runner.is_active if self._runner else False,
            get_sb_client=lambda: self._sb_client,
        )

        logger.info(
            "Worker started (max_concurrency=%d, health_port=%d)",
            self._worker_settings.max_concurrency,
            self._worker_settings.health_port,
        )

        try:
            await asyncio.gather(
                self._runner.run(),
                health_server.run(),
            )
        finally:
            await self._close()

    def request_shutdown(self) -> None:
        """Signal the worker to stop accepting new sessions and shut down.

        Safe to call from a signal handler (non-async context).
        """
        logger.info("Shutdown requested")
        self._shutdown_event.set()

    # ------------------------------------------------------------------
    # Setup / teardown helpers
    # ------------------------------------------------------------------

    async def _close(self) -> None:
        """Release Service Bus and database resources."""
        if self._sb_client is not None:
            try:
                await self._sb_client.close()
            except Exception as exc:
                logger.warning("Error closing Service Bus client: %s", exc)

        if self._credential is not None and hasattr(self._credential, "close"):
            try:
                await self._credential.close()
            except Exception as exc:
                logger.warning("Error closing credential: %s", exc)

        from backend.infrastructure.database import close_db  # noqa: PLC0415

        await close_db()
        logger.info("Worker shutdown complete")


# ---------------------------------------------------------------------------
# Process entry point
# ---------------------------------------------------------------------------


async def _async_main() -> None:
    """Configure the process and run the worker until a shutdown signal."""
    settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.app.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        force=True,
    )

    logger.info("Starting worker process")

    from backend.core.tracing import setup_tracing  # noqa: PLC0415

    setup_tracing()

    from backend.infrastructure.database import check_schema_compatibility  # noqa: PLC0415

    logger.info("Checking schema compatibility before starting worker")
    await check_schema_compatibility()
    logger.info("Schema compatibility check passed")

    from backend.infrastructure.agent_registry import register_agents  # noqa: PLC0415

    # Agent registration runs once at startup.  Any prompt or behaviour changes
    # made after this point will NOT be picked up until the worker is restarted
    # (or refresh_agents() is called explicitly).  A new Foundry agent version
    # is created automatically when the system prompt has changed.
    register_agents()

    worker = Worker()

    loop = asyncio.get_running_loop()

    def _handle_signal() -> None:
        logger.info("Received shutdown signal")
        worker.request_shutdown()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    await worker.run()


def main() -> None:
    """Synchronous entry point — called by ``python -m backend.apps.worker.main``."""
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
