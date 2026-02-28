"""
OpenTelemetry tracing setup for Azure AI Projects LLM calls.

Call ``setup_tracing()`` early — before any LLM client is created — to
auto-instrument all OpenAI / Azure AI calls with span-level telemetry.

References
----------
https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/ai/azure-ai-projects#tracing
"""

from __future__ import annotations

import logging
import os

from backend.config import get_settings

logger = logging.getLogger(__name__)


def setup_tracing() -> None:
    """Configure OpenTelemetry tracing based on application settings.
    
    This function:
    1. Sets required environment variables for the Azure AI instrumentor.
    2. Creates a ``TracerProvider`` with the chosen exporter (console / OTLP /
       Azure Monitor).
    3. Calls ``AIProjectInstrumentor().instrument()`` to auto-instrument all
       Azure AI / OpenAI SDK calls.
    """
    settings = get_settings().tracing

    if not settings.enabled:
        logger.info("Tracing is disabled (TRACING_ENABLED != true)")
        return

    # ------------------------------------------------------------------
    # 1. Environment variables expected by the Azure AI instrumentor
    # ------------------------------------------------------------------
    os.environ["AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING"] = "true"

    if settings.content_recording:
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"

    # ------------------------------------------------------------------
    # 2. Build the TracerProvider with the selected exporter
    # ------------------------------------------------------------------
    exporter_name = settings.exporter.lower()

    if exporter_name == "azure_monitor":
        _setup_azure_monitor(settings.application_insights_connection_string)
    else:
        _setup_otel_exporter(exporter_name, settings.otlp_endpoint)

    # ------------------------------------------------------------------
    # 3. Instrument Azure AI / OpenAI SDK calls
    # ------------------------------------------------------------------
    from azure.ai.projects.telemetry import AIProjectInstrumentor

    AIProjectInstrumentor().instrument()

    logger.info(
        "Tracing enabled — exporter=%s, content_recording=%s",
        exporter_name,
        settings.content_recording,
    )


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------


def _setup_azure_monitor(connection_string_override: str) -> None:
    """Configure Azure Monitor as the trace exporter.

    The connection string is resolved in this order:
    1. Explicit ``APPLICATIONINSIGHTS_CONNECTION_STRING`` env var (override).
    2. Retrieved from the AI Foundry project via
       ``project_client.telemetry.get_application_insights_connection_string()``.
    """
    conn_str = connection_string_override

    if not conn_str:
        # Retrieve from the AI Project (synchronous client needed for setup)
        try:
            from azure.ai.projects import AIProjectClient
            from azure.identity import DefaultAzureCredential

            ai_cfg = get_settings().azure_ai_project
            with (
                DefaultAzureCredential() as credential,
                AIProjectClient(
                    endpoint=ai_cfg.endpoint, credential=credential
                ) as project_client,
            ):
                conn_str = (
                    project_client.telemetry
                    .get_application_insights_connection_string()
                )
                logger.info(
                    "Retrieved Application Insights connection string from AI Project"
                )
        except Exception as exc:
            logger.warning(
                "Could not retrieve Application Insights connection string "
                "from AI Project: %s — falling back to console exporter.",
                exc,
            )
            _setup_otel_exporter("console", "")
            return

    if not conn_str:
        logger.warning(
            "TRACING_EXPORTER is 'azure_monitor' but no Application Insights "
            "connection string is available — falling back to console exporter."
        )
        _setup_otel_exporter("console", "")
        return

    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(connection_string=conn_str)
    logger.info("Azure Monitor exporter configured")


def _setup_otel_exporter(exporter_name: str, otlp_endpoint: str) -> None:
    """Configure a console or OTLP span exporter."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    if exporter_name == "otlp":
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        logger.info("OTLP exporter targeting %s", otlp_endpoint)
    else:
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        span_exporter = ConsoleSpanExporter()
        logger.info("Console span exporter configured")

    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)
