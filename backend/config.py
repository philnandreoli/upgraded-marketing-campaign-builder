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

    model_config = {"env_file": ".env", "extra": "ignore"}


class Settings(BaseSettings):
    """Aggregate settings — single entry-point for the whole app."""

    app: AppSettings = AppSettings()
    azure_ai_project: AzureAIProjectSettings = AzureAIProjectSettings()
    agent: AgentSettings = AgentSettings()
    tracing: TracingSettings = TracingSettings()
    foundry_agents: FoundryAgentsSettings = FoundryAgentsSettings()
    oidc: OIDCSettings = OIDCSettings()

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read env once)."""
    return Settings()
