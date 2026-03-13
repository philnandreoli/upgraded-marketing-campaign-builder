"""
Application configuration loaded from environment variables.
Uses pydantic-settings for validation and type coercion.
"""

from functools import lru_cache
from typing import Optional
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
    graph_client_secret: Optional[str] = Field(
        default=None,
        alias="AZURE_CLIENT_SECRET",
        description=(
            "Client secret for Microsoft Graph API access (application permissions). "
            "Required to enable the Entra ID user directory search feature. "
            "The app registration must have User.Read.All application permission with admin consent granted."
        ),
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
    auto_resume_on_startup: bool = Field(
        default=True,
        alias="AUTO_RESUME_ON_STARTUP",
        description=(
            "When true and WORKFLOW_EXECUTOR=in_process, automatically dispatch resume_pipeline "
            "jobs for any campaigns stuck in an interruptible wait state on API startup. "
            "Useful during local development with --reload to recover in-flight pipelines "
            "after a server restart. Has no effect when WORKFLOW_EXECUTOR is not in_process."
        ),
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


class CORSSettings(BaseSettings):
    """Cross-Origin Resource Sharing (CORS) configuration.

    In development the default ``["*"]`` is intentionally permissive.
    In production set ``CORS_ALLOWED_ORIGINS`` to the explicit list of
    frontend origins that are allowed to make cross-origin requests, e.g.
    ``["https://app.example.com"]``.  The value must be a JSON array string.

    When the React frontend is served by the same nginx reverse-proxy that
    proxies API traffic (the default production topology), the browser sees
    a single origin so CORS is not exercised at all.  Restricting allowed
    origins is most important when the API is accessed directly from a
    different origin (e.g. a separate staging frontend or a developer
    machine).
    """

    allowed_origins: list[str] = Field(
        default=["*"],
        alias="CORS_ALLOWED_ORIGINS",
        description=(
            'JSON array of origins allowed to make cross-origin requests, e.g. '
            '["https://app.example.com","https://admin.example.com"]. '
            'Defaults to ["*"] (all origins) which is appropriate for local '
            "development only. Always set explicit origins in production."
        ),
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


class EventSettings(BaseSettings):
    """Settings for cross-process event delivery via PostgreSQL LISTEN/NOTIFY."""

    channel_name: str = Field(
        default="workflow_events",
        alias="EVENT_CHANNEL_NAME",
        description=(
            "PostgreSQL NOTIFY channel name used for cross-process event delivery. "
            "The worker publishes to this channel; the API subscribes and forwards "
            "events to WebSocket clients."
        ),
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


class DatabaseSettings(BaseSettings):
    """Database connection settings.

    Two authentication modes are supported, controlled by ``DB_AUTH_MODE``:

    ``local`` (default)
        Traditional DATABASE_URL / password-based connection.  Set
        ``DATABASE_URL`` to point at your local PostgreSQL instance.

    ``azure``
        Microsoft Entra token-based authentication for Azure Database for
        PostgreSQL Flexible Server.  Access tokens are obtained via
        ``DefaultAzureCredential`` (managed identity / workload identity).
        Configure ``AZURE_POSTGRES_HOST``, ``AZURE_POSTGRES_DATABASE``, and
        ``AZURE_POSTGRES_USER`` instead of ``DATABASE_URL``.
    """

    mode: str = Field(
        default="local",
        alias="DB_AUTH_MODE",
        description=(
            "Database authentication mode. "
            "'local' uses DATABASE_URL/password; "
            "'azure' uses Microsoft Entra managed identity."
        ),
    )
    url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@db:5432/campaigns",
        alias="DATABASE_URL",
        description="Database connection URL (local mode only).",
    )
    azure_host: str = Field(
        default="",
        alias="AZURE_POSTGRES_HOST",
        description=(
            "Fully-qualified hostname of the Azure Database for PostgreSQL "
            "Flexible Server, e.g. myserver.postgres.database.azure.com "
            "(azure mode only)."
        ),
    )
    azure_database: str = Field(
        default="campaigns",
        alias="AZURE_POSTGRES_DATABASE",
        description="Database name on the Azure PostgreSQL server (azure mode only).",
    )
    azure_user: str = Field(
        default="",
        alias="AZURE_POSTGRES_USER",
        description=(
            "PostgreSQL username mapped to the managed identity principal "
            "(azure mode only)."
        ),
    )
    auto_migrate: bool | None = Field(
        default=None,
        alias="API_AUTO_MIGRATE",
        description=(
            "Whether to run Alembic migrations automatically on API startup. "
            "When true (local dev default), the API migrates the schema on startup. "
            "When false (azure mode default), the API validates the schema is at the "
            "expected head revision and refuses to start if mismatched — schema changes "
            "are applied exclusively by the dedicated migration job. "
            "Defaults to true when DB_AUTH_MODE=local and false when DB_AUTH_MODE=azure."
        ),
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
    cors: CORSSettings = CORSSettings()
    service_bus: ServiceBusSettings = ServiceBusSettings()
    worker: WorkerSettings = WorkerSettings()
    events: EventSettings = EventSettings()
    database: DatabaseSettings = DatabaseSettings()

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read env once)."""
    return Settings()
