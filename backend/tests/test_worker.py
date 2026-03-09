"""
Tests for the workflow-engine worker app boundary.

Covers:
- ``backend.apps.worker.dependencies.execute_job`` — coordinator dispatch routing
- ``backend.apps.worker.runner.QueueRunner``         — message handling and concurrency
- ``backend.apps.worker.main.Worker``                — initialisation and shutdown

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
    settings.events.channel_name = "workflow_events"
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

    with patch("backend.apps.worker.main.get_settings", return_value=mock_settings):
        from backend.apps.worker.main import Worker

        worker = Worker(sb_client=mock_sb_client)

    return worker, mock_sb_client


def _build_runner(
    *,
    shutdown_event: asyncio.Event | None = None,
    max_concurrency: int = 3,
    shutdown_timeout: int = 5,
    execute_job_fn=None,
) -> tuple:
    """Return (QueueRunner, mock_sb_client, shutdown_event)."""
    from backend.apps.worker.runner import QueueRunner

    mock_sb_client = MagicMock()
    event = shutdown_event if shutdown_event is not None else asyncio.Event()
    mock_execute = execute_job_fn if execute_job_fn is not None else AsyncMock()

    runner = QueueRunner(
        sb_client=mock_sb_client,
        queue_name="test-queue",
        shutdown_event=event,
        max_concurrency=max_concurrency,
        shutdown_timeout_seconds=shutdown_timeout,
        execute_job=mock_execute,
    )
    return runner, mock_sb_client, event


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
# Coordinator dispatch routing (dependencies.execute_job)
# ---------------------------------------------------------------------------


class TestDispatchRouting:
    async def test_start_pipeline_calls_run_pipeline(self):
        from backend.apps.worker.dependencies import execute_job

        mock_coord = MagicMock()
        mock_coord.run_pipeline = AsyncMock()
        mock_campaign = MagicMock()
        mock_store = MagicMock()
        mock_store.get = AsyncMock(return_value=mock_campaign)

        job = _make_job("start_pipeline", "c-1")

        with (
            patch(
                "backend.apps.worker.dependencies.CoordinatorAgent",
                return_value=mock_coord,
            ),
            patch(
                "backend.apps.worker.dependencies.get_campaign_store",
                return_value=mock_store,
            ),
        ):
            await execute_job(job)

        mock_store.get.assert_awaited_once_with("c-1")
        mock_coord.run_pipeline.assert_awaited_once_with(mock_campaign)

    async def test_start_pipeline_coordinator_has_postgres_event_callback(self):
        """execute_job creates CoordinatorAgent with a callable on_event."""
        from backend.apps.worker.dependencies import execute_job

        mock_coord = MagicMock()
        mock_coord.run_pipeline = AsyncMock()
        mock_store = MagicMock()
        mock_store.get = AsyncMock(return_value=MagicMock())

        with (
            patch(
                "backend.apps.worker.dependencies.CoordinatorAgent",
                return_value=mock_coord,
            ) as coord_cls,
            patch(
                "backend.apps.worker.dependencies.get_campaign_store",
                return_value=mock_store,
            ),
        ):
            await execute_job(_make_job("start_pipeline"))

        # on_event must be a callable (the _on_event closure), not None
        coord_cls.assert_called_once()
        _, kwargs = coord_cls.call_args
        assert kwargs.get("on_event") is not None
        assert callable(kwargs["on_event"])

    async def test_resume_pipeline_calls_resume(self):
        from backend.apps.worker.dependencies import execute_job

        mock_coord = MagicMock()
        mock_coord.resume_pipeline = AsyncMock()

        with patch(
            "backend.apps.worker.dependencies.CoordinatorAgent",
            return_value=mock_coord,
        ):
            await execute_job(_make_job("resume_pipeline", "c-2"))

        mock_coord.resume_pipeline.assert_awaited_once_with("c-2")

    async def test_retry_stage_calls_retry(self):
        from backend.apps.worker.dependencies import execute_job

        mock_coord = MagicMock()
        mock_coord.retry_current_stage = AsyncMock()

        with patch(
            "backend.apps.worker.dependencies.CoordinatorAgent",
            return_value=mock_coord,
        ):
            await execute_job(_make_job("retry_stage", "c-3"))

        mock_coord.retry_current_stage.assert_awaited_once_with("c-3")

    async def test_start_pipeline_missing_campaign_raises(self):
        from backend.apps.worker.dependencies import execute_job

        mock_coord = MagicMock()
        mock_store = MagicMock()
        mock_store.get = AsyncMock(return_value=None)

        with (
            patch(
                "backend.apps.worker.dependencies.CoordinatorAgent",
                return_value=mock_coord,
            ),
            patch(
                "backend.apps.worker.dependencies.get_campaign_store",
                return_value=mock_store,
            ),
            pytest.raises(ValueError, match="not found"),
        ):
            await execute_job(_make_job("start_pipeline", "missing"))

    async def test_unknown_action_raises(self):
        from backend.apps.worker.dependencies import execute_job

        mock_coord = MagicMock()

        job = WorkflowJob(campaign_id="c-1", action="start_pipeline")
        # Bypass the Literal validator to inject a bad action
        object.__setattr__(job, "action", "bad_action")

        with (
            patch(
                "backend.apps.worker.dependencies.CoordinatorAgent",
                return_value=mock_coord,
            ),
            pytest.raises(ValueError, match="bad_action"),
        ):
            await execute_job(job)


# ---------------------------------------------------------------------------
# Message acknowledgement (QueueRunner._run_job_task)
# ---------------------------------------------------------------------------


class TestMessageHandling:
    async def test_success_completes_message(self):
        mock_execute = AsyncMock()
        runner, _, _ = _build_runner(execute_job_fn=mock_execute)

        job = _make_job("resume_pipeline", "c-1")
        message = _make_message(job)

        mock_receiver = MagicMock()
        mock_receiver.complete_message = AsyncMock()
        mock_receiver.abandon_message = AsyncMock()

        await runner._run_job_task(mock_receiver, message, job)

        mock_receiver.complete_message.assert_awaited_once_with(message)
        mock_receiver.abandon_message.assert_not_awaited()

    async def test_failure_abandons_message(self):
        mock_execute = AsyncMock(side_effect=RuntimeError("crash"))
        runner, _, _ = _build_runner(execute_job_fn=mock_execute)

        job = _make_job("resume_pipeline", "c-1")
        message = _make_message(job)

        mock_receiver = MagicMock()
        mock_receiver.complete_message = AsyncMock()
        mock_receiver.abandon_message = AsyncMock()

        await runner._run_job_task(mock_receiver, message, job)

        mock_receiver.abandon_message.assert_awaited_once_with(message)
        mock_receiver.complete_message.assert_not_awaited()

    async def test_abandon_failure_does_not_raise(self):
        """If abandon itself fails, the task must not propagate the exception."""
        mock_execute = AsyncMock(side_effect=RuntimeError("job crash"))
        runner, _, _ = _build_runner(execute_job_fn=mock_execute)

        job = _make_job("resume_pipeline", "c-1")
        message = _make_message(job)

        mock_receiver = MagicMock()
        mock_receiver.complete_message = AsyncMock()
        mock_receiver.abandon_message = AsyncMock(side_effect=RuntimeError("bus error"))

        # Should complete without raising
        await runner._run_job_task(mock_receiver, message, job)


# ---------------------------------------------------------------------------
# Concurrency control (QueueRunner)
# ---------------------------------------------------------------------------


class TestConcurrencyLimiting:
    def test_semaphore_initial_value_equals_max_concurrency(self):
        runner, _, _ = _build_runner(max_concurrency=5)
        assert runner._semaphore._value == 5

    async def test_semaphore_limits_concurrent_executions(self):
        """At most *max_concurrency* jobs run simultaneously."""
        active = 0
        peak = 0
        gate = asyncio.Event()

        async def _slow_execute(job: WorkflowJob) -> None:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await gate.wait()
            active -= 1

        runner, _, _ = _build_runner(max_concurrency=2, execute_job_fn=_slow_execute)

        mock_receiver = MagicMock()
        mock_receiver.complete_message = AsyncMock()
        mock_receiver.abandon_message = AsyncMock()

        jobs = [_make_job("retry_stage", f"c-{i}", f"j-{i}") for i in range(4)]
        messages = [_make_message(j) for j in jobs]

        tasks = [
            asyncio.create_task(runner._run_job_task(mock_receiver, msg, job))
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
        ran: list[str] = []

        async def _track(job: WorkflowJob) -> None:
            ran.append(job.campaign_id)

        runner, _, _ = _build_runner(max_concurrency=2, execute_job_fn=_track)

        mock_receiver = MagicMock()
        mock_receiver.complete_message = AsyncMock()
        mock_receiver.abandon_message = AsyncMock()

        jobs = [_make_job("retry_stage", f"c-{i}", f"j-{i}") for i in range(5)]
        messages = [_make_message(j) for j in jobs]

        tasks = [
            asyncio.create_task(runner._run_job_task(mock_receiver, msg, job))
            for job, msg in zip(jobs, messages)
        ]
        await asyncio.gather(*tasks)

        assert sorted(ran) == [f"c-{i}" for i in range(5)]


# ---------------------------------------------------------------------------
# Graceful shutdown (QueueRunner + Worker)
# ---------------------------------------------------------------------------


class TestGracefulShutdown:
    def test_request_shutdown_sets_event(self):
        worker, _ = _build_worker()
        assert not worker._shutdown_event.is_set()
        worker.request_shutdown()
        assert worker._shutdown_event.is_set()

    async def test_receiver_loop_waits_for_active_task(self):
        """_run_receiver_loop waits for in-flight tasks before returning."""
        event = asyncio.Event()
        runner, _, _ = _build_runner(
            shutdown_event=event,
            max_concurrency=1,
            shutdown_timeout=5,
        )

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

        with patch.object(runner, "_process_next_session", side_effect=_mock_session):
            loop_task = asyncio.create_task(runner._run_receiver_loop())

            await task_started.wait()
            event.set()  # trigger shutdown

            await asyncio.wait_for(loop_task, timeout=3)

        assert task_finished.is_set()

    async def test_shutdown_timeout_cancels_remaining_tasks(self):
        """Tasks are cancelled when shutdown_timeout_seconds is exceeded."""
        event = asyncio.Event()
        runner, _, _ = _build_runner(
            shutdown_event=event,
            max_concurrency=1,
            shutdown_timeout=0,
        )

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

        with patch.object(runner, "_process_next_session", side_effect=_hanging_session):
            loop_task = asyncio.create_task(runner._run_receiver_loop())

            await task_started.wait()
            event.set()  # trigger shutdown

            await asyncio.wait_for(loop_task, timeout=5)

        assert task_cancelled.is_set()


# ---------------------------------------------------------------------------
# Worker initialisation
# ---------------------------------------------------------------------------


class TestWorkerInit:
    def test_runner_is_none_before_run(self):
        worker, _ = _build_worker()
        assert worker._runner is None

    def test_shutdown_event_clear_on_init(self):
        worker, _ = _build_worker()
        assert not worker._shutdown_event.is_set()

    def test_custom_sb_client_stored(self):
        worker, sb = _build_worker()
        assert worker._sb_client is sb


# ---------------------------------------------------------------------------
# HealthServer — readiness endpoint
# ---------------------------------------------------------------------------


def _make_health_server(
    *,
    db_ok: bool = True,
    schema_ok: bool = True,
    receiver_active: bool = True,
    sb_client: object = object(),
) -> "HealthServer":
    """Build a HealthServer wired with simple mock callbacks."""
    from backend.apps.worker.health import HealthServer

    shutdown_event = asyncio.Event()
    server = HealthServer(
        port=19998,
        shutdown_event=shutdown_event,
        get_receiver_active=lambda: receiver_active,
        get_sb_client=lambda: sb_client,
    )
    return server


class TestHealthServerReady:
    """HealthServer._handle_health_ready returns correct status codes."""

    async def _get_ready(self, server: "HealthServer"):
        """Invoke _handle_health_ready and return the aiohttp Response."""
        from unittest.mock import MagicMock

        return await server._handle_health_ready(MagicMock())

    async def test_ready_when_all_checks_pass(self):
        from unittest.mock import AsyncMock, patch

        server = _make_health_server()

        with (
            patch.object(server, "_check_db_health", new=AsyncMock(return_value=True)),
            patch.object(server, "_check_schema_health", new=AsyncMock(return_value=True)),
        ):
            response = await self._get_ready(server)

        assert response.status == 200
        import json
        body = json.loads(response.body)
        assert body["status"] == "ready"
        assert body["schema"] is True
        assert body["db"] is True
        assert body["receiver"] is True

    async def test_not_ready_when_db_fails(self):
        from unittest.mock import AsyncMock, patch

        server = _make_health_server()

        with (
            patch.object(server, "_check_db_health", new=AsyncMock(return_value=False)),
            patch.object(server, "_check_schema_health", new=AsyncMock(return_value=True)),
        ):
            response = await self._get_ready(server)

        assert response.status == 503
        import json
        body = json.loads(response.body)
        assert body["status"] == "not_ready"
        assert body["db"] is False

    async def test_not_ready_when_schema_fails(self):
        from unittest.mock import AsyncMock, patch

        server = _make_health_server()

        with (
            patch.object(server, "_check_db_health", new=AsyncMock(return_value=True)),
            patch.object(server, "_check_schema_health", new=AsyncMock(return_value=False)),
        ):
            response = await self._get_ready(server)

        assert response.status == 503
        import json
        body = json.loads(response.body)
        assert body["status"] == "not_ready"
        assert body["schema"] is False

    async def test_not_ready_when_receiver_inactive(self):
        from unittest.mock import AsyncMock, patch

        server = _make_health_server(receiver_active=False)

        with (
            patch.object(server, "_check_db_health", new=AsyncMock(return_value=True)),
            patch.object(server, "_check_schema_health", new=AsyncMock(return_value=True)),
        ):
            response = await self._get_ready(server)

        assert response.status == 503
        import json
        body = json.loads(response.body)
        assert body["status"] == "not_ready"
        assert body["receiver"] is False

    async def test_schema_health_returns_true_on_success(self):
        from unittest.mock import AsyncMock, patch

        server = _make_health_server()

        with patch(
            "backend.infrastructure.database.check_schema_compatibility",
            new=AsyncMock(return_value=None),
        ):
            result = await server._check_schema_health()

        assert result is True

    async def test_schema_health_returns_false_on_failure(self):
        from unittest.mock import AsyncMock, patch

        server = _make_health_server()

        with patch(
            "backend.infrastructure.database.check_schema_compatibility",
            new=AsyncMock(side_effect=RuntimeError("Schema mismatch")),
        ):
            result = await server._check_schema_health()

        assert result is False


# ---------------------------------------------------------------------------
# Worker startup — no migrations, schema check only
# ---------------------------------------------------------------------------


class TestWorkerStartupNomigrations:
    """_async_main must call check_schema_compatibility, never init_db."""

    async def test_async_main_calls_check_schema_compatibility(self):
        """Worker startup invokes check_schema_compatibility (not init_db)."""
        import backend.apps.worker.main as worker_main

        called = []

        async def _fake_check():
            called.append("check_schema_compatibility")

        def _fake_register():
            pass

        mock_worker = MagicMock()
        mock_worker.run = AsyncMock()

        with (
            patch("backend.apps.worker.main.get_settings", return_value=_make_settings()),
            patch("backend.core.tracing.setup_tracing"),
            patch(
                "backend.infrastructure.database.check_schema_compatibility",
                new=_fake_check,
            ),
            patch("backend.infrastructure.agent_registry.register_agents", new=_fake_register),
            patch("backend.apps.worker.main.Worker", return_value=mock_worker),
        ):
            await worker_main._async_main()

        assert "check_schema_compatibility" in called, (
            "check_schema_compatibility must be called during worker startup"
        )
