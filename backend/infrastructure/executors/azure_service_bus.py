"""
Azure Service Bus WorkflowExecutor implementation.

Dispatches pipeline jobs by publishing them as messages to an Azure Service Bus
queue, allowing decoupled, durable processing across multiple worker instances.

Authentication uses ``DefaultAzureCredential`` when
``AZURE_SERVICE_BUS_NAMESPACE`` is configured (preferred for Azure-hosted
deployments with managed identity).  Set ``AZURE_SERVICE_BUS_CONNECTION_STRING``
instead to use a connection string (useful for local development).

Queue infrastructure concerns (TTL, dead-lettering, max delivery count) are
configured on the queue itself, not enforced in this code.  Recommended values:
- Message TTL: 24 hours
- Max delivery count: 3
- Dead-letter on expiration: enabled
"""

from __future__ import annotations

import logging

from azure.identity.aio import DefaultAzureCredential
from azure.servicebus.aio import ServiceBusClient, ServiceBusSender
from azure.servicebus import ServiceBusMessage

from backend.config import get_settings
from backend.infrastructure.workflow_executor import WorkflowJob

logger = logging.getLogger(__name__)


class AzureServiceBusExecutor:
    """Enqueues workflow jobs on an Azure Service Bus queue.

    Uses ``DefaultAzureCredential`` when a namespace is configured (managed
    identity / workload identity), otherwise falls back to a connection string.
    The sender is created lazily on first use and reused across calls.
    """

    def __init__(self) -> None:
        settings = get_settings()
        cfg = settings.service_bus
        self._queue_name = cfg.queue_name
        self._sender: ServiceBusSender | None = None

        if cfg.namespace:
            self._credential: DefaultAzureCredential | None = DefaultAzureCredential()
            self._client = ServiceBusClient(
                fully_qualified_namespace=cfg.namespace,
                credential=self._credential,
            )
            logger.debug(
                "AzureServiceBusExecutor initialised with managed-identity auth "
                "(namespace=%s, queue=%s)",
                cfg.namespace,
                cfg.queue_name,
            )
        elif cfg.connection_string:
            self._credential = None
            self._client = ServiceBusClient.from_connection_string(cfg.connection_string)
            logger.debug(
                "AzureServiceBusExecutor initialised with connection-string auth "
                "(queue=%s)",
                cfg.queue_name,
            )
        else:
            raise ValueError(
                "AzureServiceBusExecutor requires either AZURE_SERVICE_BUS_NAMESPACE "
                "or AZURE_SERVICE_BUS_CONNECTION_STRING to be set."
            )

    # ------------------------------------------------------------------
    # WorkflowExecutor protocol
    # ------------------------------------------------------------------

    async def dispatch(self, job: WorkflowJob) -> None:
        """Publish *job* to the configured Service Bus queue and return immediately.

        The message is sent with:

        - ``session_id`` = ``campaign_id`` — ensures FIFO ordering per campaign
          (the queue must have sessions enabled).
        - ``message_id`` = ``job_id`` — Service Bus deduplication key.
        - ``content_type`` = ``"application/json"``.
        """
        sender = await self._get_sender()
        payload = job.model_dump_json()
        message = ServiceBusMessage(
            body=payload,
            session_id=job.campaign_id,
            message_id=job.job_id,
            content_type="application/json",
        )
        await sender.send_messages(message)
        logger.debug(
            "Dispatched job job_id=%s campaign_id=%s action=%s to queue=%s",
            job.job_id,
            job.campaign_id,
            job.action,
            self._queue_name,
        )

    async def close(self) -> None:
        """Close the underlying Service Bus sender and client, releasing connections."""
        if self._sender is not None:
            await self._sender.close()
            self._sender = None
        await self._client.close()
        if self._credential is not None and hasattr(self._credential, "close"):
            await self._credential.close()

    async def health_check(self) -> bool:
        """Return ``True`` when the Service Bus sender is open and reachable.

        Returns ``False`` if the sender has been closed or the queue is
        unreachable (e.g. misconfigured namespace / connection string).

        The check reads the ``_is_closed`` attribute on the SDK sender object.
        This is a private attribute but is the only practical way to inspect
        sender liveness without sending a real message.  ``getattr`` with a
        ``False`` default ensures the check degrades gracefully if the attribute
        is removed in a future SDK release (treats absence as healthy).
        """
        try:
            sender = await self._get_sender()
            return not getattr(sender, "_is_closed", False)
        except Exception as exc:
            logger.warning("AzureServiceBusExecutor health check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_sender(self) -> ServiceBusSender:
        """Return the cached sender, creating it on first call."""
        if self._sender is None:
            self._sender = self._client.get_queue_sender(queue_name=self._queue_name)
        return self._sender
