"""
Application configuration loaded from environment variables.
Uses pydantic-settings for validation and type coercion.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field


class AzureAIProjectSettings(BaseSettings):
    """Azure AI Foundry project connection settings."""

    endpoint: str = Field(..., alias="AZURE_AI_PROJECT_ENDPOINT")
    deployment_name: str = Field(
        default="gpt-4", alias="AZURE_AI_MODEL_DEPLOYMENT_NAME"
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


class AgentSettings(BaseSettings):
    """Agent behaviour settings."""

    max_retries: int = Field(default=3, alias="AGENT_MAX_RETRIES")
    temperature: float = Field(default=0.7, alias="AGENT_TEMPERATURE")
    max_tokens: int = Field(default=4096, alias="AGENT_MAX_TOKENS")
    pipeline_idle_timeout_days: int = Field(
        default=30,
        alias="PIPELINE_IDLE_TIMEOUT_DAYS",
        description=(
            "Days to wait for human input (clarification / content approval) before "
            "transitioning the campaign to MANUAL_REVIEW_REQUIRED. Default: 30 days."
        ),
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


class TracingSettings(BaseSettings):
    """OpenTelemetry tracing settings."""

    enabled: bool = Field(default=False, alias="TRACING_ENABLED")
    exporter: str = Field(
        default="console",
        alias="TRACING_EXPORTER",
        description="One of: console, otlp, azure_monitor",
    )
    otlp_endpoint: str = Field(
        default="http://localhost:4317", alias="OTLP_ENDPOINT"
    )
    application_insights_connection_string: str = Field(
        default="", alias="APPLICATIONINSIGHTS_CONNECTION_STRING"
    )
    content_recording: bool = Field(
        default=True, alias="TRACING_CONTENT_RECORDING"
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


class OIDCSettings(BaseSettings):
    """OIDC / OAuth 2.0 authentication settings."""

    enabled: bool = Field(
        default=False,
        alias="AUTH_ENABLED",
        description="Enable JWT authentication for all campaign endpoints.",
    )
    authority: str = Field(
        default="",
        alias="OIDC_AUTHORITY",
        description="OIDC authority URL, e.g. https://login.microsoftonline.com/{tenant_id}/v2.0",
    )
    client_id: str = Field(
        default="",
        alias="OIDC_CLIENT_ID",
        description="Application (client) ID registered in the identity provider.",
    )
    jwks_cache_ttl: int = Field(
        default=3600,
        alias="OIDC_JWKS_CACHE_TTL",
        description="Seconds to cache the OIDC provider's public keys (default: 3600).",
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


class FoundryAgentsSettings(BaseSettings):
    """AI Foundry Agent Operations settings."""

    enabled: bool = Field(
        default=False,
        alias="FOUNDRY_AGENTS_ENABLED",
        description="Register marketing agents as Foundry Agent versions on startup.",
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


class AppSettings(BaseSettings):
    """Top-level application settings."""

    env: str = Field(default="development", alias="APP_ENV")
    port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="APP_LOG_LEVEL")
    workflow_executor: str = Field(
        default="in_process",
        alias="WORKFLOW_EXECUTOR",
        description="Executor backend for pipeline jobs. One of: in_process, azure_service_bus.",
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


class ServiceBusSettings(BaseSettings):
    """Azure Service Bus settings (used when WORKFLOW_EXECUTOR=azure_service_bus)."""

    namespace: str = Field(
        default="",
        alias="AZURE_SERVICE_BUS_NAMESPACE",
        description=(
            "Fully-qualified Service Bus namespace hostname, e.g. "
            "mybus.servicebus.windows.net. "
            "Takes precedence over connection_string when both are set."
        ),
    )
    connection_string: str = Field(
        default="",
        alias="AZURE_SERVICE_BUS_CONNECTION_STRING",
        description="Service Bus connection string. Used when namespace is not set.",
    )
    queue_name: str = Field(
        default="workflow-jobs",
        alias="AZURE_SERVICE_BUS_QUEUE_NAME",
        description="Name of the Service Bus queue that receives workflow jobs.",
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


class WorkerSettings(BaseSettings):
    """Settings for the standalone worker process (backend/worker.py)."""

    max_concurrency: int = Field(
        default=3,
        alias="WORKER_MAX_CONCURRENCY",
        description="Maximum number of simultaneous pipeline executions.",
    )
    shutdown_timeout_seconds: int = Field(
        default=300,
        alias="WORKER_SHUTDOWN_TIMEOUT_SECONDS",
        description="Seconds to wait for active jobs to finish during graceful shutdown.",
    )
    health_port: int = Field(
        default=8001,
        alias="WORKER_HEALTH_PORT",
        description="TCP port for the worker health HTTP endpoint (GET /health/live, /health/ready).",
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


class Settings(BaseSettings):
    """Aggregate settings — single entry-point for the whole app."""

    app: AppSettings = AppSettings()
    azure_ai_project: AzureAIProjectSettings = AzureAIProjectSettings()
    agent: AgentSettings = AgentSettings()
    tracing: TracingSettings = TracingSettings()
    foundry_agents: FoundryAgentsSettings = FoundryAgentsSettings()
    oidc: OIDCSettings = OIDCSettings()
    service_bus: ServiceBusSettings = ServiceBusSettings()
    worker: WorkerSettings = WorkerSettings()

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read env once)."""
    return Settings()
