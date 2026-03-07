"""
WorkflowExecutor abstraction layer.

Defines the ``WorkflowJob`` model and ``WorkflowExecutor`` Protocol so that
the API layer can request pipeline execution without being coupled to a
specific execution strategy (in-process background task, Azure Service Bus, etc.).

Usage::

    from backend.services.workflow_executor import get_executor, WorkflowJob

    executor = get_executor()
    job = WorkflowJob(campaign_id="abc-123", action="start_pipeline")
    await executor.dispatch(job)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from backend.config import get_settings


# ---------------------------------------------------------------------------
# WorkflowJob — the unit of work handed to the executor
# ---------------------------------------------------------------------------


class WorkflowJob(BaseModel):
    """Represents a single pipeline execution request."""

    job_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this job (UUID, auto-generated).",
    )
    campaign_id: str = Field(description="ID of the campaign this job targets.")
    action: Literal["start_pipeline", "resume_pipeline", "retry_stage"] = Field(
        description="The pipeline operation to perform."
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the job was created.",
    )


# ---------------------------------------------------------------------------
# WorkflowExecutor — protocol every execution backend must satisfy
# ---------------------------------------------------------------------------


@runtime_checkable
class WorkflowExecutor(Protocol):
    """Protocol that every executor implementation must satisfy.

    Implementations must be async-compatible and support dispatch, graceful
    shutdown, and readiness probing.
    """

    async def dispatch(self, job: WorkflowJob) -> None:
        """Enqueue or directly execute *job*."""
        ...

    async def close(self) -> None:
        """Release resources held by this executor (connections, threads, etc.)."""
        ...

    async def health_check(self) -> bool:
        """Return ``True`` when the executor is ready to accept jobs."""
        ...


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_executor() -> WorkflowExecutor:
    """Return the configured ``WorkflowExecutor`` implementation.

    Reads ``WORKFLOW_EXECUTOR`` from the application settings:

    - ``in_process``  — (default) no external infrastructure required.
    - ``azure_service_bus`` — enqueues jobs on an Azure Service Bus queue.

    Raises ``ValueError`` for unknown executor types.
    """
    settings = get_settings()
    executor_type = settings.app.workflow_executor

    if executor_type == "in_process":
        from backend.services.executors.in_process import InProcessExecutor  # noqa: PLC0415

        return InProcessExecutor()

    if executor_type == "azure_service_bus":
        from backend.services.executors.azure_service_bus import AzureServiceBusExecutor  # noqa: PLC0415

        return AzureServiceBusExecutor()

    raise ValueError(
        f"Unknown WORKFLOW_EXECUTOR value: {executor_type!r}. "
        "Supported values: 'in_process', 'azure_service_bus'."
    )
