"""
Runtime dependency construction for the workflow-engine worker.

Contains factory functions that build the Service Bus client and execute
workflow jobs by dispatching them to the coordinator pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.config import get_settings
from backend.infrastructure.campaign_store import get_campaign_store
from backend.infrastructure.event_store import get_event_store
from backend.infrastructure.workflow_executor import WorkflowJob
from backend.orchestration.coordinator_agent import CoordinatorAgent

logger = logging.getLogger(__name__)


async def build_sb_client(
    namespace: str | None,
    connection_string: str | None,
    credential_holder: list[Any],
) -> Any:
    """Build a ``ServiceBusClient`` from environment configuration.

    When *namespace* is provided the client is authenticated via
    ``DefaultAzureCredential`` (managed identity / workload identity) and the
    credential object is appended to *credential_holder* so the caller can
    close it on shutdown.  When *connection_string* is provided the client is
    built from the connection string directly.

    Raises
    ------
    ValueError
        When neither *namespace* nor *connection_string* is set.
    """
    from azure.servicebus.aio import ServiceBusClient  # noqa: PLC0415

    if namespace:
        from azure.identity.aio import DefaultAzureCredential  # noqa: PLC0415

        credential = DefaultAzureCredential()
        credential_holder.append(credential)
        logger.debug(
            "Connecting to Service Bus with managed-identity auth (namespace=%s)",
            namespace,
        )
        return ServiceBusClient(
            fully_qualified_namespace=namespace,
            credential=credential,
        )

    if connection_string:
        logger.debug("Connecting to Service Bus via connection string")
        return ServiceBusClient.from_connection_string(connection_string)

    raise ValueError(
        "Worker requires either AZURE_SERVICE_BUS_NAMESPACE "
        "or AZURE_SERVICE_BUS_CONNECTION_STRING to be set."
    )


async def execute_job(job: WorkflowJob) -> None:
    """Dispatch *job* to the coordinator pipeline.

    Creates a fresh ``CoordinatorAgent`` with a ``PostgresEventPublisher``
    so that real-time pipeline events are forwarded to the API process via
    PostgreSQL LISTEN/NOTIFY and then relayed to WebSocket clients.
    Each event is also persisted to the ``campaign_events`` table via
    ``EventStore`` so that the audit trail survives browser refreshes.
    """
    from backend.infrastructure.database import engine  # noqa: PLC0415
    from backend.infrastructure.event_publisher import PostgresEventPublisher  # noqa: PLC0415

    settings = get_settings()
    publisher = PostgresEventPublisher(
        engine,
        channel_name=settings.events.channel_name,
    )
    event_store = get_event_store()

    store = get_campaign_store()
    campaign = await store.get(job.campaign_id)
    workspace_id: str | None = getattr(campaign, "workspace_id", None)

    async def _on_event(event: str, data: dict) -> None:
        enriched = data if "workspace_id" in data else {**data, "workspace_id": workspace_id}
        await publisher.publish(event, enriched)
        campaign_id = enriched.get("campaign_id", job.campaign_id)
        stage = enriched.get("stage")
        owner_id = enriched.get("owner_id")
        try:
            await event_store.save_event(
                campaign_id=campaign_id,
                event_type=event,
                payload=enriched,
                stage=stage,
                owner_id=owner_id,
            )
        except Exception:
            logger.exception("EventStore.save_event failed for event %s", event)

    coordinator = CoordinatorAgent(on_event=_on_event)

    if job.action == "start_pipeline":
        if campaign is None:
            raise ValueError(
                f"Campaign {job.campaign_id!r} not found for start_pipeline"
            )
        await coordinator.run_pipeline(campaign)

    elif job.action == "resume_pipeline":
        await coordinator.resume_pipeline(job.campaign_id)

    elif job.action == "retry_stage":
        await coordinator.retry_current_stage(job.campaign_id)

    else:
        raise ValueError(f"Unknown action: {job.action!r}")
