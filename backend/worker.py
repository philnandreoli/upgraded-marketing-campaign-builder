"""
Standalone worker process for pipeline job execution.

Connects to an Azure Service Bus session queue and processes ``WorkflowJob``
messages by dispatching them to the ``CoordinatorAgent`` pipeline.  Intended
to run as a separate deployment unit alongside the FastAPI web process.

Run with::

    python -m backend.worker
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from aiohttp import web
from azure.servicebus import NEXT_AVAILABLE_SESSION
from azure.servicebus.exceptions import OperationTimeoutError

from backend.orchestration.coordinator_agent import CoordinatorAgent
from backend.config import get_settings
from backend.infrastructure.campaign_store import get_campaign_store
from backend.infrastructure.event_publisher import PostgresEventPublisher
from backend.infrastructure.workflow_executor import WorkflowJob

logger = logging.getLogger(__name__)


class Worker:
    """Session-aware Service Bus worker that executes pipeline jobs.

    Each message on the queue represents a ``WorkflowJob``.  The worker
    accepts sessions (one per campaign), processes their messages, and
    dispatches the jobs to the coordinator pipeline.

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

        self._semaphore = asyncio.Semaphore(self._worker_settings.max_concurrency)
        self._shutdown_event = asyncio.Event()
        self._active_tasks: set[asyncio.Task[Any]] = set()

        # Service Bus client — injected for testing, otherwise created in run()
        self._sb_client = sb_client
        self._credential: Any = None
        self._receiver_active = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Initialise the Service Bus connection and start processing.

        Returns once graceful shutdown completes.
        """
        if self._sb_client is None:
            self._sb_client = await self._create_sb_client()

        self._receiver_active = True
        logger.info(
            "Worker started (max_concurrency=%d, health_port=%d)",
            self._worker_settings.max_concurrency,
            self._worker_settings.health_port,
        )

        try:
            await asyncio.gather(
                self._run_receiver_loop(),
                self._run_health_server(),
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
    # Receiver loop
    # ------------------------------------------------------------------

    async def _run_receiver_loop(self) -> None:
        """Maintain up to *max_concurrency* concurrent session processors."""
        while not self._shutdown_event.is_set():
            active = {t for t in self._active_tasks if not t.done()}

            while (
                len(active) < self._worker_settings.max_concurrency
                and not self._shutdown_event.is_set()
            ):
                task = asyncio.create_task(self._process_next_session())
                self._active_tasks.add(task)
                task.add_done_callback(self._active_tasks.discard)
                active.add(task)

            # Short sleep to avoid a tight spin while waiting for shutdown
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._shutdown_event.wait()),
                    timeout=0.5,
                )
            except asyncio.TimeoutError:
                pass

        # Graceful shutdown: let active tasks finish (or timeout)
        pending = {t for t in self._active_tasks if not t.done()}
        if pending:
            timeout = self._worker_settings.shutdown_timeout_seconds
            logger.info(
                "Waiting for %d active task(s) to complete (timeout=%ds)…",
                len(pending),
                timeout,
            )
            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending, return_exceptions=True),
                    timeout=float(timeout),
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Shutdown timeout exceeded; cancelling %d remaining task(s)",
                    len([t for t in pending if not t.done()]),
                )
                for task in pending:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

        self._receiver_active = False
        logger.info("Receiver loop finished")

    async def _process_next_session(self) -> None:
        """Accept one Service Bus session and process all its messages.

        Uses ``NEXT_AVAILABLE_SESSION`` so the broker assigns the next
        session that has pending messages.  Returns when the session is
        exhausted (no new messages within *max_wait_time*) or the worker
        is shutting down.
        """
        try:
            async with self._sb_client.get_queue_receiver(
                queue_name=self._sb_settings.queue_name,
                session_id=NEXT_AVAILABLE_SESSION,
                max_wait_time=30,
            ) as receiver:
                job_tasks: set[asyncio.Task[Any]] = set()

                async for message in receiver:
                    if self._shutdown_event.is_set():
                        await receiver.abandon_message(message)
                        break

                    try:
                        body = b"".join(message.body)
                        job = WorkflowJob.model_validate_json(body)
                    except Exception:
                        logger.exception("Failed to deserialise message body; abandoning")
                        await receiver.abandon_message(message)
                        continue

                    task = asyncio.create_task(
                        self._run_job_task(receiver, message, job)
                    )
                    job_tasks.add(task)
                    task.add_done_callback(job_tasks.discard)

                # Keep the receiver open until all in-session job tasks finish
                if job_tasks:
                    await asyncio.gather(*job_tasks, return_exceptions=True)

        except OperationTimeoutError:
            # No sessions currently available — brief pause before the
            # caller spawns a new attempt.
            await asyncio.sleep(1)
        except Exception:
            logger.exception("Unexpected error in session processor; backing off")
            await asyncio.sleep(5)

    async def _run_job_task(self, receiver: Any, message: Any, job: WorkflowJob) -> None:
        """Execute a single job under the concurrency semaphore.

        Completes the message on success or abandons it on failure so the
        broker can redeliver (up to its configured max-delivery-count).
        """
        async with self._semaphore:
            try:
                await self._execute_job(job)
                await receiver.complete_message(message)
                logger.debug(
                    "Completed job_id=%s campaign_id=%s action=%s",
                    job.job_id,
                    job.campaign_id,
                    job.action,
                )
            except Exception:
                logger.exception(
                    "Job failed — abandoning job_id=%s campaign_id=%s action=%s",
                    job.job_id,
                    job.campaign_id,
                    job.action,
                )
                try:
                    await receiver.abandon_message(message)
                except Exception:
                    logger.warning(
                        "Could not abandon message for job_id=%s", job.job_id
                    )

    async def _execute_job(self, job: WorkflowJob) -> None:
        """Dispatch *job* to the coordinator pipeline.

        Creates a fresh ``CoordinatorAgent`` with a ``PostgresEventPublisher``
        so that real-time pipeline events are forwarded to the API process via
        PostgreSQL LISTEN/NOTIFY and then relayed to WebSocket clients.
        """
        from backend.infrastructure.database import engine  # noqa: PLC0415

        settings = get_settings()
        publisher = PostgresEventPublisher(
            engine,
            channel_name=settings.events.channel_name,
        )

        async def _on_event(event: str, data: dict) -> None:
            await publisher.publish(event, data)

        coordinator = CoordinatorAgent(on_event=_on_event)
        store = get_campaign_store()

        if job.action == "start_pipeline":
            campaign = await store.get(job.campaign_id)
            if campaign is None:
                raise ValueError(
                    f"Campaign {job.campaign_id!r} not found for start_pipeline"
                )
            await coordinator.run_pipeline(campaign)

        elif job.action == "resume_pipeline":
            await coordinator.resume_pipeline(job.campaign_id)

        elif job.action == "retry_stage":
            await coordinator.retry_current_stage(job.campaign_id)

        else:
            raise ValueError(f"Unknown action: {job.action!r}")

    # ------------------------------------------------------------------
    # Health server
    # ------------------------------------------------------------------

    async def _run_health_server(self) -> None:
        """Run a lightweight aiohttp health HTTP server.

        Endpoints:

        - ``GET /health/live``  — process is running.
        - ``GET /health/ready`` — DB reachable and queue receiver active.
        """
        app = web.Application()
        app.router.add_get("/health/live", self._handle_health_live)
        app.router.add_get("/health/ready", self._handle_health_ready)

        runner = web.AppRunner(app)
        await runner.setup()
        port = self._worker_settings.health_port
        # Bind to all interfaces so container orchestrators (Kubernetes,
        # Azure Container Apps) can reach the health endpoints from outside
        # the container network namespace.
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info("Health server listening on port %d", port)

        try:
            await self._shutdown_event.wait()
        finally:
            await runner.cleanup()

    async def _handle_health_live(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "alive"})

    async def _handle_health_ready(self, _request: web.Request) -> web.Response:
        db_ok = await self._check_db_health()
        receiver_ok = self._receiver_active and self._sb_client is not None

        if db_ok and receiver_ok:
            return web.json_response({"status": "ready", "db": True, "receiver": True})

        return web.json_response(
            {"status": "not_ready", "db": db_ok, "receiver": receiver_ok},
            status=503,
        )

    async def _check_db_health(self) -> bool:
        """Return ``True`` when the database is reachable."""
        try:
            import sqlalchemy  # noqa: PLC0415
            from backend.infrastructure.database import engine  # noqa: PLC0415

            async with engine.connect() as conn:
                await conn.execute(sqlalchemy.text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning("DB health check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Setup / teardown helpers
    # ------------------------------------------------------------------

    async def _create_sb_client(self) -> Any:
        """Build a ``ServiceBusClient`` from environment configuration."""
        from azure.servicebus.aio import ServiceBusClient  # noqa: PLC0415

        cfg = self._sb_settings
        if cfg.namespace:
            from azure.identity.aio import DefaultAzureCredential  # noqa: PLC0415

            self._credential = DefaultAzureCredential()
            logger.debug(
                "Connecting to Service Bus with managed-identity auth (namespace=%s)",
                cfg.namespace,
            )
            return ServiceBusClient(
                fully_qualified_namespace=cfg.namespace,
                credential=self._credential,
            )

        if cfg.connection_string:
            logger.debug("Connecting to Service Bus via connection string")
            return ServiceBusClient.from_connection_string(cfg.connection_string)

        raise ValueError(
            "Worker requires either AZURE_SERVICE_BUS_NAMESPACE "
            "or AZURE_SERVICE_BUS_CONNECTION_STRING to be set."
        )

    async def _close(self) -> None:
        """Release Service Bus and database resources."""
        self._receiver_active = False

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

    from backend.infrastructure.database import init_db  # noqa: PLC0415

    await init_db()

    from backend.infrastructure.agent_registry import register_agents  # noqa: PLC0415

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
    """Synchronous entry point — called by ``python -m backend.worker``."""
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
