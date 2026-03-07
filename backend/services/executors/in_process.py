"""
In-process WorkflowExecutor implementation.

Dispatches pipeline jobs directly within the current process using
FastAPI's ``BackgroundTasks`` or an equivalent in-process mechanism.
This executor requires no external infrastructure and is the default
for local development and single-instance deployments.

.. note::
    Full implementation is tracked in a follow-up issue.
    This module exists to satisfy the ``get_executor()`` factory introduced
    alongside the ``WorkflowExecutor`` Protocol.
"""

from __future__ import annotations

from backend.services.workflow_executor import WorkflowJob


class InProcessExecutor:
    """Executes workflow jobs in the same process as the API server."""

    async def dispatch(self, job: WorkflowJob) -> None:
        """Enqueue *job* for in-process execution."""
        raise NotImplementedError("InProcessExecutor.dispatch is not yet implemented.")

    async def close(self) -> None:
        """No resources to release for in-process execution."""

    async def health_check(self) -> bool:
        """Always healthy — no external dependencies."""
        return True
