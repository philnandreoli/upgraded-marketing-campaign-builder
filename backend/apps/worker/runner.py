"""
Queue session runner for the workflow-engine worker.

Manages the Service Bus session receiver loop: accepts sessions, processes
messages, and dispatches jobs to the coordinator pipeline via an injected
``execute_job`` callable.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine

from azure.servicebus import NEXT_AVAILABLE_SESSION
from azure.servicebus.exceptions import OperationTimeoutError

from backend.infrastructure.workflow_executor import WorkflowJob

logger = logging.getLogger(__name__)


class QueueRunner:
    """Session-aware receiver loop over a Service Bus queue.

    Maintains up to *max_concurrency* concurrent session processors.  Each
    session processor accepts one Service Bus session and executes all of its
    messages as independent :class:`WorkflowJob` tasks.

    Parameters
    ----------
    sb_client:
        Live ``ServiceBusClient`` instance to receive messages from.
    queue_name:
        Name of the Service Bus queue to receive from.
    shutdown_event:
        Shared :class:`asyncio.Event` that signals the worker is shutting
        down.  The runner drains active tasks and returns when the event is
        set.
    max_concurrency:
        Maximum number of simultaneous pipeline executions.
    shutdown_timeout_seconds:
        Seconds to wait for active tasks to finish during graceful shutdown
        before they are cancelled.
    execute_job:
        Async callable that dispatches a :class:`WorkflowJob` to the
        pipeline.  Injected to allow the caller to swap implementations
        (e.g. for testing).
    """

    def __init__(
        self,
        *,
        sb_client: Any,
        queue_name: str,
        shutdown_event: asyncio.Event,
        max_concurrency: int,
        shutdown_timeout_seconds: int,
        execute_job: Callable[[WorkflowJob], Coroutine[Any, Any, None]],
    ) -> None:
        self._sb_client = sb_client
        self._queue_name = queue_name
        self._shutdown_event = shutdown_event
        self._max_concurrency = max_concurrency
        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._execute_job_fn = execute_job

        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._active_tasks: set[asyncio.Task[Any]] = set()
        self._active = False

    @property
    def is_active(self) -> bool:
        """``True`` while the receiver loop is running."""
        return self._active

    async def run(self) -> None:
        """Run the receiver loop until shutdown is requested."""
        self._active = True
        try:
            await self._run_receiver_loop()
        finally:
            self._active = False

    # ------------------------------------------------------------------
    # Receiver loop
    # ------------------------------------------------------------------

    async def _run_receiver_loop(self) -> None:
        """Maintain up to *max_concurrency* concurrent session processors."""
        while not self._shutdown_event.is_set():
            active = {t for t in self._active_tasks if not t.done()}

            while (
                len(active) < self._max_concurrency
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
            timeout = self._shutdown_timeout_seconds
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
                queue_name=self._queue_name,
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
                await self._execute_job_fn(job)
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
