"""
In-process WorkflowExecutor implementation.

Dispatches pipeline jobs directly within the current process by scheduling
asyncio tasks.  This executor requires no external infrastructure and is
the default for local development and single-instance deployments.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.agents.coordinator_agent import CoordinatorAgent
from backend.api.websocket import manager as ws_manager
from backend.services.campaign_store import get_campaign_store
from backend.services.event_publisher import InProcessEventPublisher
from backend.services.workflow_executor import WorkflowJob

logger = logging.getLogger(__name__)


class InProcessExecutor:
    """Executes workflow jobs in the same process as the API server.

    Each dispatched job becomes an :func:`asyncio.ensure_future` task so the
    HTTP response is returned immediately while the pipeline runs in the
    background — identical behaviour to the previous ``BackgroundTasks``
    approach, but routed through the ``WorkflowExecutor`` abstraction.
    """

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()

    # ------------------------------------------------------------------
    # WorkflowExecutor protocol
    # ------------------------------------------------------------------

    async def dispatch(self, job: WorkflowJob) -> None:
        """Schedule *job* as an asyncio task and return immediately."""
        task = asyncio.ensure_future(self._run_job(job))
        self._tasks.add(task)
        # Remove completed tasks from the set automatically to avoid unbounded growth
        task.add_done_callback(self._tasks.discard)

    async def close(self) -> None:
        """Cancel any still-running tasks and wait for them to finish."""
        pending = [t for t in self._tasks if not t.done()]
        if not pending:
            return

        logger.info("InProcessExecutor.close(): cancelling %d pending task(s)", len(pending))
        for task in pending:
            task.cancel()

        results = await asyncio.gather(*pending, return_exceptions=True)
        for task, result in zip(pending, results):
            if isinstance(result, asyncio.CancelledError):
                logger.info("Task %s was cancelled during shutdown", task.get_name())
            elif isinstance(result, Exception):
                logger.warning("Task %s raised during shutdown: %s", task.get_name(), result)

    async def health_check(self) -> bool:
        """Always healthy — no external dependencies."""
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_job(self, job: WorkflowJob) -> None:
        """Execute *job* inside the current process.

        Mirrors the exception-handling pattern of ``_run_pipeline()`` in
        ``backend/api/campaigns.py``: any exception is logged rather than
        re-raised so that a pipeline failure never kills the event loop.
        """
        publisher = InProcessEventPublisher(ws_manager)

        async def _broadcast(event: str, data: dict[str, Any]) -> None:
            await publisher.publish(event, data)

        coordinator = CoordinatorAgent(on_event=_broadcast)
        store = get_campaign_store()

        try:
            if job.action == "start_pipeline":
                campaign = await store.get(job.campaign_id)
                if campaign is None:
                    logger.error(
                        "InProcessExecutor: campaign %s not found for start_pipeline",
                        job.campaign_id,
                    )
                    return
                logger.info("InProcessExecutor: starting pipeline for campaign %s", job.campaign_id)
                await coordinator.run_pipeline(campaign)
                logger.info("InProcessExecutor: pipeline completed for campaign %s", job.campaign_id)

            elif job.action == "resume_pipeline":
                logger.info("InProcessExecutor: resuming pipeline for campaign %s", job.campaign_id)
                await coordinator.resume_pipeline(job.campaign_id)
                logger.info(
                    "InProcessExecutor: pipeline resumed/completed for campaign %s", job.campaign_id
                )

            elif job.action == "retry_stage":
                logger.info(
                    "InProcessExecutor: retrying current stage for campaign %s", job.campaign_id
                )
                await coordinator.retry_current_stage(job.campaign_id)
                logger.info(
                    "InProcessExecutor: stage retry completed for campaign %s", job.campaign_id
                )

            else:
                logger.error(
                    "InProcessExecutor: unknown action %r for job %s", job.action, job.job_id
                )

        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "InProcessExecutor: pipeline crashed for campaign %s (job %s): %s",
                job.campaign_id,
                job.job_id,
                exc,
            )
