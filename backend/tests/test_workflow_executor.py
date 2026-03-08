"""
Tests for backend.services.workflow_executor.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch

from backend.services.workflow_executor import WorkflowJob, WorkflowExecutor, get_executor


# ---------------------------------------------------------------------------
# WorkflowJob tests
# ---------------------------------------------------------------------------


class TestWorkflowJob:
    def test_auto_generates_job_id(self):
        job = WorkflowJob(campaign_id="camp-1", action="start_pipeline")
        assert job.job_id  # non-empty
        assert len(job.job_id) == 36  # UUID4 string length

    def test_job_ids_are_unique(self):
        j1 = WorkflowJob(campaign_id="camp-1", action="start_pipeline")
        j2 = WorkflowJob(campaign_id="camp-1", action="start_pipeline")
        assert j1.job_id != j2.job_id

    def test_explicit_job_id(self):
        job = WorkflowJob(job_id="my-id", campaign_id="camp-1", action="start_pipeline")
        assert job.job_id == "my-id"

    def test_created_at_is_set(self):
        job = WorkflowJob(campaign_id="camp-1", action="start_pipeline")
        assert job.created_at is not None

    def test_valid_actions(self):
        for action in ("start_pipeline", "resume_pipeline", "retry_stage"):
            job = WorkflowJob(campaign_id="camp-1", action=action)  # type: ignore[arg-type]
            assert job.action == action

    def test_invalid_action_raises(self):
        with pytest.raises(Exception):
            WorkflowJob(campaign_id="camp-1", action="unknown_action")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# WorkflowExecutor Protocol tests
# ---------------------------------------------------------------------------


class TestWorkflowExecutorProtocol:
    def test_protocol_is_runtime_checkable(self):
        """A class implementing the three async methods satisfies the Protocol."""

        class _Impl:
            async def dispatch(self, job: WorkflowJob) -> None: ...
            async def close(self) -> None: ...
            async def health_check(self) -> bool: return True

        assert isinstance(_Impl(), WorkflowExecutor)

    def test_incomplete_class_fails_protocol_check(self):
        """A class missing required methods does not satisfy the Protocol."""

        class _Incomplete:
            async def dispatch(self, job: WorkflowJob) -> None: ...
            # missing close and health_check

        assert not isinstance(_Incomplete(), WorkflowExecutor)


# ---------------------------------------------------------------------------
# get_executor factory tests
# ---------------------------------------------------------------------------


def _make_settings(executor_type: str):
    """Return a mock settings object with the given executor type."""
    from unittest.mock import MagicMock
    settings = MagicMock()
    settings.app.workflow_executor = executor_type
    return settings


class TestGetExecutor:
    def test_in_process_executor_returned(self):
        from backend.services.executors.in_process import InProcessExecutor

        with patch("backend.infrastructure.workflow_executor.get_settings", return_value=_make_settings("in_process")):
            executor = get_executor()
        assert isinstance(executor, InProcessExecutor)

    def test_unknown_executor_raises(self):
        with patch("backend.infrastructure.workflow_executor.get_settings", return_value=_make_settings("unsupported_backend")):
            with pytest.raises(ValueError, match="Unknown WORKFLOW_EXECUTOR"):
                get_executor()
