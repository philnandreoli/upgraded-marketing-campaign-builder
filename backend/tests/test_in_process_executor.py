"""
Unit tests for InProcessExecutor.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from typing import Literal

import pytest

from backend.services.executors.in_process import InProcessExecutor
from backend.services.workflow_executor import WorkflowJob


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(action: Literal["start_pipeline", "resume_pipeline", "retry_stage"] = "start_pipeline", campaign_id: str = "camp-1") -> WorkflowJob:
    return WorkflowJob(campaign_id=campaign_id, action=action)


def _mock_coordinator(*, run_pipeline=None, resume_pipeline=None, retry_current_stage=None):
    coord = MagicMock()
    coord.run_pipeline = run_pipeline or AsyncMock()
    coord.resume_pipeline = resume_pipeline or AsyncMock()
    coord.retry_current_stage = retry_current_stage or AsyncMock()
    return coord


# ---------------------------------------------------------------------------
# dispatch — task creation and action routing
# ---------------------------------------------------------------------------


class TestDispatch:
    async def test_dispatch_creates_task(self):
        """dispatch() must schedule an asyncio task (non-blocking)."""
        executor = InProcessExecutor()

        mock_coord = _mock_coordinator()
        mock_store = MagicMock()
        mock_store.get = AsyncMock(return_value=MagicMock())

        with (
            patch("backend.services.executors.in_process.CoordinatorAgent", return_value=mock_coord),
            patch("backend.services.executors.in_process.get_campaign_store", return_value=mock_store),
            patch("backend.services.executors.in_process.ws_manager"),
        ):
            job = _make_job("start_pipeline")
            await executor.dispatch(job)
            # Give the scheduled task a chance to run
            await asyncio.sleep(0)

        mock_store.get.assert_awaited_once_with("camp-1")
        mock_coord.run_pipeline.assert_awaited_once()

    async def test_dispatch_returns_immediately_without_blocking(self):
        """dispatch() must return before the task completes."""
        executor = InProcessExecutor()

        ran = []

        async def _slow_run_pipeline(campaign):
            await asyncio.sleep(0.05)
            ran.append(True)

        mock_coord = _mock_coordinator(run_pipeline=_slow_run_pipeline)
        mock_store = MagicMock()
        mock_store.get = AsyncMock(return_value=MagicMock())

        with (
            patch("backend.services.executors.in_process.CoordinatorAgent", return_value=mock_coord),
            patch("backend.services.executors.in_process.get_campaign_store", return_value=mock_store),
            patch("backend.services.executors.in_process.ws_manager"),
        ):
            await executor.dispatch(_make_job("start_pipeline"))
            # The task has been scheduled but not completed yet
            assert ran == []
            # Allow it to complete
            await asyncio.sleep(0.1)

        assert ran == [True]

    async def test_start_pipeline_calls_run_pipeline(self):
        executor = InProcessExecutor()
        campaign_mock = MagicMock()
        mock_coord = _mock_coordinator()
        mock_store = MagicMock()
        mock_store.get = AsyncMock(return_value=campaign_mock)

        with (
            patch("backend.services.executors.in_process.CoordinatorAgent", return_value=mock_coord),
            patch("backend.services.executors.in_process.get_campaign_store", return_value=mock_store),
            patch("backend.services.executors.in_process.ws_manager"),
        ):
            await executor.dispatch(_make_job("start_pipeline", "c-1"))
            await asyncio.sleep(0)

        mock_coord.run_pipeline.assert_awaited_once_with(campaign_mock)

    async def test_resume_pipeline_calls_coordinator_resume(self):
        executor = InProcessExecutor()
        mock_coord = _mock_coordinator()
        mock_store = MagicMock()

        with (
            patch("backend.services.executors.in_process.CoordinatorAgent", return_value=mock_coord),
            patch("backend.services.executors.in_process.get_campaign_store", return_value=mock_store),
            patch("backend.services.executors.in_process.ws_manager"),
        ):
            await executor.dispatch(_make_job("resume_pipeline", "c-2"))
            await asyncio.sleep(0)

        mock_coord.resume_pipeline.assert_awaited_once_with("c-2")

    async def test_retry_stage_calls_coordinator_retry(self):
        executor = InProcessExecutor()
        mock_coord = _mock_coordinator()
        mock_store = MagicMock()

        with (
            patch("backend.services.executors.in_process.CoordinatorAgent", return_value=mock_coord),
            patch("backend.services.executors.in_process.get_campaign_store", return_value=mock_store),
            patch("backend.services.executors.in_process.ws_manager"),
        ):
            await executor.dispatch(_make_job("retry_stage", "c-3"))
            await asyncio.sleep(0)

        mock_coord.retry_current_stage.assert_awaited_once_with("c-3")

    async def test_start_pipeline_missing_campaign_logs_error(self, caplog):
        """If the campaign is not found for start_pipeline the error is logged, not raised."""
        import logging
        executor = InProcessExecutor()
        mock_coord = _mock_coordinator()
        mock_store = MagicMock()
        mock_store.get = AsyncMock(return_value=None)  # campaign not found

        with (
            patch("backend.services.executors.in_process.CoordinatorAgent", return_value=mock_coord),
            patch("backend.services.executors.in_process.get_campaign_store", return_value=mock_store),
            patch("backend.services.executors.in_process.ws_manager"),
            caplog.at_level(logging.ERROR, logger="backend.services.executors.in_process"),
        ):
            await executor.dispatch(_make_job("start_pipeline", "missing-id"))
            await asyncio.sleep(0)

        mock_coord.run_pipeline.assert_not_awaited()
        assert "missing-id" in caplog.text


# ---------------------------------------------------------------------------
# close — task cancellation
# ---------------------------------------------------------------------------


class TestClose:
    async def test_close_no_pending_tasks_is_noop(self):
        """close() must be safe to call when there are no active tasks."""
        executor = InProcessExecutor()
        await executor.close()  # should not raise

    async def test_close_cancels_pending_tasks(self):
        """close() must cancel tasks that have not yet completed."""
        executor = InProcessExecutor()

        started = asyncio.Event()
        cancelled_flag = []

        async def _long_running(*_args, **_kwargs):
            started.set()
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled_flag.append(True)
                raise

        mock_coord = _mock_coordinator(run_pipeline=_long_running)
        mock_store = MagicMock()
        mock_store.get = AsyncMock(return_value=MagicMock())

        with (
            patch("backend.services.executors.in_process.CoordinatorAgent", return_value=mock_coord),
            patch("backend.services.executors.in_process.get_campaign_store", return_value=mock_store),
            patch("backend.services.executors.in_process.ws_manager"),
        ):
            await executor.dispatch(_make_job("start_pipeline"))
            await started.wait()  # Ensure the task is actually running before we close
            await executor.close()

        assert cancelled_flag == [True]

    async def test_close_awaits_all_pending_tasks(self):
        """close() must wait for each task to acknowledge cancellation."""
        executor = InProcessExecutor()

        mock_coord = _mock_coordinator()
        # Make the task take a few event-loop cycles to respond to cancellation
        async def _slow_cancel(*_args, **_kwargs):
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                await asyncio.sleep(0)
                raise

        mock_coord.run_pipeline = _slow_cancel
        mock_store = MagicMock()
        mock_store.get = AsyncMock(return_value=MagicMock())

        with (
            patch("backend.services.executors.in_process.CoordinatorAgent", return_value=mock_coord),
            patch("backend.services.executors.in_process.get_campaign_store", return_value=mock_store),
            patch("backend.services.executors.in_process.ws_manager"),
        ):
            await executor.dispatch(_make_job("start_pipeline"))
            await asyncio.sleep(0)  # let the task start
            await executor.close()

        # After close(), no pending tasks should remain
        assert all(t.done() for t in executor._tasks)


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    async def test_health_check_always_true(self):
        executor = InProcessExecutor()
        assert await executor.health_check() is True


# ---------------------------------------------------------------------------
# error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    async def test_pipeline_exception_is_logged_not_raised(self, caplog):
        """Exceptions from coordinator methods must be caught and logged."""
        import logging
        executor = InProcessExecutor()

        mock_coord = _mock_coordinator(
            run_pipeline=AsyncMock(side_effect=RuntimeError("boom"))
        )
        mock_store = MagicMock()
        mock_store.get = AsyncMock(return_value=MagicMock())

        with (
            patch("backend.services.executors.in_process.CoordinatorAgent", return_value=mock_coord),
            patch("backend.services.executors.in_process.get_campaign_store", return_value=mock_store),
            patch("backend.services.executors.in_process.ws_manager"),
            caplog.at_level(logging.ERROR, logger="backend.services.executors.in_process"),
        ):
            await executor.dispatch(_make_job("start_pipeline", "err-camp"))
            await asyncio.sleep(0)

        assert "err-camp" in caplog.text
        assert "boom" in caplog.text

    async def test_task_exception_does_not_affect_other_tasks(self):
        """A failing task must not prevent a subsequent task from running."""
        executor = InProcessExecutor()

        second_ran = []

        async def _fail(*_args, **_kwargs):
            raise RuntimeError("first task fails")

        async def _ok(*_args, **_kwargs):
            second_ran.append(True)

        call_count = 0

        class _CoordFactory:
            def __init__(self, *, on_event=None):
                nonlocal call_count
                call_count += 1
                self.run_pipeline = AsyncMock(side_effect=_fail if call_count == 1 else _ok)

        mock_store = MagicMock()
        mock_store.get = AsyncMock(return_value=MagicMock())

        with (
            patch("backend.services.executors.in_process.CoordinatorAgent", _CoordFactory),
            patch("backend.services.executors.in_process.get_campaign_store", return_value=mock_store),
            patch("backend.services.executors.in_process.ws_manager"),
        ):
            await executor.dispatch(_make_job("start_pipeline", "c-fail"))
            await executor.dispatch(_make_job("start_pipeline", "c-ok"))
            await asyncio.sleep(0)

        assert second_ran == [True]
