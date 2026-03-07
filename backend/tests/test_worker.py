"""
Tests for backend.worker — standalone pipeline worker process.

All tests run fully offline: Service Bus and DB connections are mocked so
no Azure infrastructure is required.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.workflow_executor import WorkflowJob


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job(
    action: str = "start_pipeline",
    campaign_id: str = "camp-1",
    job_id: str = "job-1",
) -> WorkflowJob:
    return WorkflowJob(job_id=job_id, campaign_id=campaign_id, action=action)


def _make_message(job: WorkflowJob) -> MagicMock:
    """Return a mock Service Bus message whose body is the JSON-encoded job."""
    msg = MagicMock()
    payload = job.model_dump_json().encode()
    msg.body = iter([payload])
    return msg


def _make_worker_settings(
    *,
    max_concurrency: int = 3,
    shutdown_timeout: int = 5,
    health_port: int = 19999,
) -> MagicMock:
    ws = MagicMock()
    ws.max_concurrency = max_concurrency
    ws.shutdown_timeout_seconds = shutdown_timeout
    ws.health_port = health_port
    return ws


def _make_settings(
    *,
    max_concurrency: int = 3,
    shutdown_timeout: int = 5,
    health_port: int = 19999,
) -> MagicMock:
    settings = MagicMock()
    settings.app.log_level = "INFO"
    settings.service_bus.queue_name = "test-queue"
    settings.worker = _make_worker_settings(
        max_concurrency=max_concurrency,
        shutdown_timeout=shutdown_timeout,
        health_port=health_port,
    )
    return settings


def _build_worker(
    *,
    max_concurrency: int = 3,
    shutdown_timeout: int = 5,
    health_port: int = 19999,
) -> tuple:
    """Return (Worker instance, mock_sb_client) with patched settings."""
    mock_sb_client = MagicMock()
    mock_sb_client.close = AsyncMock()

    mock_settings = _make_settings(
        max_concurrency=max_concurrency,
        shutdown_timeout=shutdown_timeout,
        health_port=health_port,
    )

    with patch("backend.worker.get_settings", return_value=mock_settings):
        from backend.worker import Worker

        worker = Worker(sb_client=mock_sb_client)

    return worker, mock_sb_client


# ---------------------------------------------------------------------------
# WorkflowJob deserialization
# ---------------------------------------------------------------------------


class TestJobDeserialization:
    def test_start_pipeline_roundtrip(self):
        job = _make_job("start_pipeline", "camp-1", "j-1")
        result = WorkflowJob.model_validate_json(job.model_dump_json())
        assert result.action == "start_pipeline"
        assert result.campaign_id == "camp-1"
        assert result.job_id == "j-1"

    def test_resume_pipeline_roundtrip(self):
        job = _make_job("resume_pipeline", "camp-2")
        result = WorkflowJob.model_validate_json(job.model_dump_json())
        assert result.action == "resume_pipeline"
        assert result.campaign_id == "camp-2"

    def test_retry_stage_roundtrip(self):
        job = _make_job("retry_stage", "camp-3")
        result = WorkflowJob.model_validate_json(job.model_dump_json())
        assert result.action == "retry_stage"
        assert result.campaign_id == "camp-3"

    def test_all_fields_preserved(self):
        job = _make_job("start_pipeline", "camp-x", "unique-id")
        result = WorkflowJob.model_validate_json(job.model_dump_json())
        assert result.job_id == job.job_id
        assert result.campaign_id == job.campaign_id
        assert result.action == job.action
        assert result.created_at == job.created_at


# ---------------------------------------------------------------------------
# Coordinator dispatch routing (_execute_job)
# ---------------------------------------------------------------------------


class TestDispatchRouting:
    async def test_start_pipeline_calls_run_pipeline(self):
        worker, _ = _build_worker()
        mock_coord = MagicMock()
        mock_coord.run_pipeline = AsyncMock()
        mock_campaign = MagicMock()
        mock_store = MagicMock()
        mock_store.get = AsyncMock(return_value=mock_campaign)

        job = _make_job("start_pipeline", "c-1")

        with (
            patch("backend.worker.CoordinatorAgent", return_value=mock_coord),
            patch("backend.worker.get_campaign_store", return_value=mock_store),
        ):
            await worker._execute_job(job)

        mock_store.get.assert_awaited_once_with("c-1")
        mock_coord.run_pipeline.assert_awaited_once_with(mock_campaign)

    async def test_start_pipeline_coordinator_has_postgres_event_callback(self):
        """Worker creates CoordinatorAgent with a PostgresEventPublisher-backed on_event."""
        worker, _ = _build_worker()
        mock_coord = MagicMock()
        mock_coord.run_pipeline = AsyncMock()
        mock_store = MagicMock()
        mock_store.get = AsyncMock(return_value=MagicMock())

        mock_engine = MagicMock()

        with (
            patch("backend.worker.CoordinatorAgent", return_value=mock_coord) as coord_cls,
            patch("backend.worker.get_campaign_store", return_value=mock_store),
            patch("backend.worker.engine", mock_engine, create=True),
        ):
            await worker._execute_job(_make_job("start_pipeline"))

        # on_event must be a callable (the _on_event closure), not None
        coord_cls.assert_called_once()
        _, kwargs = coord_cls.call_args
        assert kwargs.get("on_event") is not None
        assert callable(kwargs["on_event"])

    async def test_resume_pipeline_calls_resume(self):
        worker, _ = _build_worker()
        mock_coord = MagicMock()
        mock_coord.resume_pipeline = AsyncMock()

        with patch("backend.worker.CoordinatorAgent", return_value=mock_coord):
            await worker._execute_job(_make_job("resume_pipeline", "c-2"))

        mock_coord.resume_pipeline.assert_awaited_once_with("c-2")

    async def test_retry_stage_calls_retry(self):
        worker, _ = _build_worker()
        mock_coord = MagicMock()
        mock_coord.retry_current_stage = AsyncMock()

        with patch("backend.worker.CoordinatorAgent", return_value=mock_coord):
            await worker._execute_job(_make_job("retry_stage", "c-3"))

        mock_coord.retry_current_stage.assert_awaited_once_with("c-3")

    async def test_start_pipeline_missing_campaign_raises(self):
        worker, _ = _build_worker()
        mock_coord = MagicMock()
        mock_store = MagicMock()
        mock_store.get = AsyncMock(return_value=None)

        with (
            patch("backend.worker.CoordinatorAgent", return_value=mock_coord),
            patch("backend.worker.get_campaign_store", return_value=mock_store),
            pytest.raises(ValueError, match="not found"),
        ):
            await worker._execute_job(_make_job("start_pipeline", "missing"))

    async def test_unknown_action_raises(self):
        worker, _ = _build_worker()
        mock_coord = MagicMock()

        job = WorkflowJob(campaign_id="c-1", action="start_pipeline")
        # Bypass the Literal validator to inject a bad action
        object.__setattr__(job, "action", "bad_action")

        with (
            patch("backend.worker.CoordinatorAgent", return_value=mock_coord),
            pytest.raises(ValueError, match="bad_action"),
        ):
            await worker._execute_job(job)


# ---------------------------------------------------------------------------
# Message acknowledgement (_run_job_task)
# ---------------------------------------------------------------------------


class TestMessageHandling:
    async def test_success_completes_message(self):
        worker, _ = _build_worker()
        job = _make_job("resume_pipeline", "c-1")
        message = _make_message(job)

        mock_receiver = MagicMock()
        mock_receiver.complete_message = AsyncMock()
        mock_receiver.abandon_message = AsyncMock()

        mock_coord = MagicMock()
        mock_coord.resume_pipeline = AsyncMock()

        with patch("backend.worker.CoordinatorAgent", return_value=mock_coord):
            await worker._run_job_task(mock_receiver, message, job)

        mock_receiver.complete_message.assert_awaited_once_with(message)
        mock_receiver.abandon_message.assert_not_awaited()

    async def test_failure_abandons_message(self):
        worker, _ = _build_worker()
        job = _make_job("resume_pipeline", "c-1")
        message = _make_message(job)

        mock_receiver = MagicMock()
        mock_receiver.complete_message = AsyncMock()
        mock_receiver.abandon_message = AsyncMock()

        mock_coord = MagicMock()
        mock_coord.resume_pipeline = AsyncMock(side_effect=RuntimeError("crash"))

        with patch("backend.worker.CoordinatorAgent", return_value=mock_coord):
            await worker._run_job_task(mock_receiver, message, job)

        mock_receiver.abandon_message.assert_awaited_once_with(message)
        mock_receiver.complete_message.assert_not_awaited()

    async def test_abandon_failure_does_not_raise(self):
        """If abandon itself fails, the task must not propagate the exception."""
        worker, _ = _build_worker()
        job = _make_job("resume_pipeline", "c-1")
        message = _make_message(job)

        mock_receiver = MagicMock()
        mock_receiver.complete_message = AsyncMock()
        mock_receiver.abandon_message = AsyncMock(side_effect=RuntimeError("bus error"))

        mock_coord = MagicMock()
        mock_coord.resume_pipeline = AsyncMock(side_effect=RuntimeError("job crash"))

        with patch("backend.worker.CoordinatorAgent", return_value=mock_coord):
            # Should complete without raising
            await worker._run_job_task(mock_receiver, message, job)


# ---------------------------------------------------------------------------
# Concurrency control
# ---------------------------------------------------------------------------


class TestConcurrencyLimiting:
    def test_semaphore_initial_value_equals_max_concurrency(self):
        worker, _ = _build_worker(max_concurrency=5)
        assert worker._semaphore._value == 5

    async def test_semaphore_limits_concurrent_executions(self):
        """At most *max_concurrency* jobs run simultaneously."""
        worker, _ = _build_worker(max_concurrency=2)

        active = 0
        peak = 0
        gate = asyncio.Event()

        async def _slow_execute(job: WorkflowJob) -> None:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await gate.wait()
            active -= 1

        mock_receiver = MagicMock()
        mock_receiver.complete_message = AsyncMock()
        mock_receiver.abandon_message = AsyncMock()

        jobs = [_make_job("retry_stage", f"c-{i}", f"j-{i}") for i in range(4)]
        messages = [_make_message(j) for j in jobs]

        with patch.object(worker, "_execute_job", side_effect=_slow_execute):
            tasks = [
                asyncio.create_task(worker._run_job_task(mock_receiver, msg, job))
                for job, msg in zip(jobs, messages)
            ]
            # Let tasks acquire the semaphore
            await asyncio.sleep(0.05)

            assert active <= 2  # no more than max_concurrency concurrently

            gate.set()
            await asyncio.gather(*tasks, return_exceptions=True)

        assert peak <= 2

    async def test_all_jobs_eventually_complete(self):
        """All jobs run even when max_concurrency < total jobs."""
        worker, _ = _build_worker(max_concurrency=2)
        ran: list[str] = []

        async def _track(job: WorkflowJob) -> None:
            ran.append(job.campaign_id)

        mock_receiver = MagicMock()
        mock_receiver.complete_message = AsyncMock()
        mock_receiver.abandon_message = AsyncMock()

        jobs = [_make_job("retry_stage", f"c-{i}", f"j-{i}") for i in range(5)]
        messages = [_make_message(j) for j in jobs]

        with patch.object(worker, "_execute_job", side_effect=_track):
            tasks = [
                asyncio.create_task(worker._run_job_task(mock_receiver, msg, job))
                for job, msg in zip(jobs, messages)
            ]
            await asyncio.gather(*tasks)

        assert sorted(ran) == [f"c-{i}" for i in range(5)]


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------


class TestGracefulShutdown:
    def test_request_shutdown_sets_event(self):
        worker, _ = _build_worker()
        assert not worker._shutdown_event.is_set()
        worker.request_shutdown()
        assert worker._shutdown_event.is_set()

    async def test_receiver_loop_waits_for_active_task(self):
        """_run_receiver_loop waits for in-flight tasks before returning."""
        worker, _ = _build_worker(max_concurrency=1, shutdown_timeout=5)

        task_started = asyncio.Event()
        task_finished = asyncio.Event()

        call_count = 0

        async def _mock_session() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                task_started.set()
                await asyncio.sleep(0.1)
                task_finished.set()
            else:
                # Subsequent calls block until shutdown
                await asyncio.sleep(10)

        with patch.object(worker, "_process_next_session", side_effect=_mock_session):
            loop_task = asyncio.create_task(worker._run_receiver_loop())

            await task_started.wait()
            worker.request_shutdown()

            await asyncio.wait_for(loop_task, timeout=3)

        assert task_finished.is_set()

    async def test_shutdown_timeout_cancels_remaining_tasks(self):
        """Tasks are cancelled when shutdown_timeout_seconds is exceeded."""
        worker, _ = _build_worker(max_concurrency=1, shutdown_timeout=0)

        task_started = asyncio.Event()
        task_cancelled = asyncio.Event()

        call_count = 0

        async def _hanging_session() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                task_started.set()
                try:
                    await asyncio.sleep(999)
                except asyncio.CancelledError:
                    task_cancelled.set()
                    raise
            else:
                await asyncio.sleep(999)

        with patch.object(worker, "_process_next_session", side_effect=_hanging_session):
            loop_task = asyncio.create_task(worker._run_receiver_loop())

            await task_started.wait()
            worker.request_shutdown()

            await asyncio.wait_for(loop_task, timeout=5)

        assert task_cancelled.is_set()


# ---------------------------------------------------------------------------
# Worker initialisation
# ---------------------------------------------------------------------------


class TestWorkerInit:
    def test_default_semaphore_value(self):
        worker, _ = _build_worker(max_concurrency=3)
        assert worker._semaphore._value == 3

    def test_receiver_inactive_before_run(self):
        worker, _ = _build_worker()
        assert worker._receiver_active is False

    def test_shutdown_event_clear_on_init(self):
        worker, _ = _build_worker()
        assert not worker._shutdown_event.is_set()

    def test_custom_sb_client_stored(self):
        _, mock_sb = _build_worker()
        # The injected mock client is stored internally
        worker, sb = _build_worker()
        assert worker._sb_client is sb
