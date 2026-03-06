"""
Azure Service Bus WorkflowExecutor implementation.

Dispatches pipeline jobs by publishing them as messages to an Azure Service Bus
queue, allowing decoupled, durable processing across multiple worker instances.

.. note::
    Full implementation is tracked in a follow-up issue.
    This module exists to satisfy the ``get_executor()`` factory introduced
    alongside the ``WorkflowExecutor`` Protocol.
"""

from __future__ import annotations

from backend.services.workflow_executor import WorkflowJob


class AzureServiceBusExecutor:
    """Enqueues workflow jobs on an Azure Service Bus queue."""

    async def dispatch(self, job: WorkflowJob) -> None:
        """Publish *job* to the configured Service Bus queue."""
        raise NotImplementedError("AzureServiceBusExecutor.dispatch is not yet implemented.")

    async def close(self) -> None:
        """Close the underlying Service Bus client and release connections."""
        raise NotImplementedError("AzureServiceBusExecutor.close is not yet implemented.")

    async def health_check(self) -> bool:
        """Return ``True`` when the Service Bus connection is healthy."""
        raise NotImplementedError("AzureServiceBusExecutor.health_check is not yet implemented.")
