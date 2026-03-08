"""
SQLAlchemy async engine & session factory for PostgreSQL.

Two authentication modes are supported, controlled by the ``DB_AUTH_MODE``
environment variable:

``local`` (default)
    Traditional ``DATABASE_URL`` / password-based connection.  Set
    ``DATABASE_URL`` to point at your local PostgreSQL instance.

``azure``
    Microsoft Entra token-based authentication for Azure Database for
    PostgreSQL Flexible Server.  A short-lived access token is acquired via
    ``DefaultAzureCredential`` (managed identity / workload identity) and
    supplied to asyncpg as the connection password on each new connection.
    Configure ``AZURE_POSTGRES_HOST``, ``AZURE_POSTGRES_DATABASE``, and
    ``AZURE_POSTGRES_USER`` instead of ``DATABASE_URL``.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, AsyncGenerator, Callable, Coroutine

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

if TYPE_CHECKING:
    from azure.identity.aio import DefaultAzureCredential

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authentication-mode constants
# ---------------------------------------------------------------------------

_DB_AUTH_MODE_LOCAL = "local"
_DB_AUTH_MODE_AZURE = "azure"

# OAuth 2.0 scope required for Azure Database for PostgreSQL token auth.
_ENTRA_TOKEN_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"

# ---------------------------------------------------------------------------
# Backward-compatible DATABASE_URL
# ---------------------------------------------------------------------------

# Kept as a module-level constant so that legacy imports and shims continue
# to work.  In azure mode this reflects the local-development default and
# should not be used directly; use get_connection_dsn() instead.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/campaigns",
)

# ---------------------------------------------------------------------------
# Azure credential (lazy, module-level singleton)
# ---------------------------------------------------------------------------

# Initialised on first call to _fetch_entra_db_token(); closed in close_db().
_entra_credential: "DefaultAzureCredential | None" = None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _get_auth_mode() -> str:
    """Return the current database authentication mode (lower-cased)."""
    return os.getenv("DB_AUTH_MODE", _DB_AUTH_MODE_LOCAL).lower()


def _build_azure_db_url() -> str:
    """Build the asyncpg SQLAlchemy URL for Azure Database for PostgreSQL."""
    host = os.getenv("AZURE_POSTGRES_HOST", "")
    database = os.getenv("AZURE_POSTGRES_DATABASE", "campaigns")
    user = os.getenv("AZURE_POSTGRES_USER", "")
    return f"postgresql+asyncpg://{user}@{host}/{database}"


async def _fetch_entra_db_token() -> str:
    """Acquire a Microsoft Entra access token for Azure Database for PostgreSQL.

    asyncpg calls this coroutine on each new connection when it is supplied as
    the ``password`` connect argument.  ``DefaultAzureCredential`` handles
    token caching and refresh internally, so there is no need to re-create the
    credential object per call.
    """
    global _entra_credential
    if _entra_credential is None:
        from azure.identity.aio import DefaultAzureCredential  # noqa: PLC0415

        _entra_credential = DefaultAzureCredential()
        logger.debug("Initialised DefaultAzureCredential for PostgreSQL Entra auth")

    token = await _entra_credential.get_token(_ENTRA_TOKEN_SCOPE)
    return token.token


def _create_engine():
    """Create the async SQLAlchemy engine, choosing auth mode from DB_AUTH_MODE."""
    mode = _get_auth_mode()
    if mode == _DB_AUTH_MODE_AZURE:
        url = _build_azure_db_url()
        logger.info(
            "Database engine: azure Entra mode (host=%s)",
            os.getenv("AZURE_POSTGRES_HOST", "<unset>"),
        )
        return create_async_engine(
            url,
            echo=False,
            future=True,
            connect_args={
                "password": _fetch_entra_db_token,
                "ssl": "require",
            },
        )

    # Local / default: password-based DATABASE_URL.
    logger.debug("Database engine: local mode")
    return create_async_engine(DATABASE_URL, echo=False, future=True)


def get_connection_dsn() -> str:
    """Return an asyncpg-compatible DSN for direct asyncpg connections.

    In local mode this is derived from ``DATABASE_URL``.  In azure mode it is
    built from ``AZURE_POSTGRES_HOST``, ``AZURE_POSTGRES_DATABASE``, and
    ``AZURE_POSTGRES_USER`` (no password embedded — use
    :func:`get_connection_password` to supply the token callback).
    """
    if _get_auth_mode() == _DB_AUTH_MODE_AZURE:
        host = os.getenv("AZURE_POSTGRES_HOST", "")
        database = os.getenv("AZURE_POSTGRES_DATABASE", "campaigns")
        user = os.getenv("AZURE_POSTGRES_USER", "")
        return f"postgresql://{user}@{host}/{database}"
    return DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def get_connection_password() -> "Callable[[], Coroutine[Any, Any, str]] | None":
    """Return the asyncpg password callable for azure mode, or ``None`` for local.

    The returned coroutine function acquires a fresh Microsoft Entra access
    token each time it is awaited.  Pass it to ``asyncpg.connect()`` as the
    ``password`` keyword argument so that asyncpg calls it on each new
    connection.

    Returns ``None`` in local mode (asyncpg uses the password embedded in the
    DSN instead).
    """
    if _get_auth_mode() == _DB_AUTH_MODE_AZURE:
        return _fetch_entra_db_token
    return None


engine = _create_engine()

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Declarative base & table
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class WorkspaceRow(Base):
    """A workspace that groups campaigns and members together."""

    __tablename__ = "workspaces"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    owner_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    is_personal = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class WorkspaceMemberRow(Base):
    """Join table: associates users with workspaces and records a per-workspace role."""

    __tablename__ = "workspace_members"

    workspace_id = Column(String, ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role = Column(String, nullable=False)
    added_at = Column(DateTime, nullable=False)


class CampaignRow(Base):
    """Single-table design: indexed id/status + full document in JSONB."""

    __tablename__ = "campaigns"

    id = Column(String, primary_key=True)
    owner_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, index=True)
    data = Column(Text, nullable=False)  # JSON text of the full Campaign
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=True, index=True)


class UserRow(Base):
    """Persisted platform user created JIT on first authentication."""

    __tablename__ = "users"

    id = Column(String, primary_key=True)           # OIDC oid/sub
    email = Column(String, nullable=True, index=True)
    display_name = Column(String, nullable=True)
    role = Column(String, nullable=False, default="viewer")
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)


class CampaignMemberRow(Base):
    """Join table: associates users with campaigns and records a per-campaign role."""

    __tablename__ = "campaign_members"

    campaign_id = Column(String, ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role = Column(String, nullable=False)   # "owner", "editor", "viewer"
    added_at = Column(DateTime, nullable=False)


class WorkflowSignalRow(Base):
    """One row per human-input signal (clarification answer or content approval)."""

    __tablename__ = "workflow_signals"

    id = Column(String, primary_key=True)  # UUID
    campaign_id = Column(String, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    signal_type = Column(String, nullable=False)  # "clarification_response" | "content_approval"
    payload = Column(Text, nullable=False)  # JSON-serialised signal data
    created_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)  # null = pending, set = consumed

    __table_args__ = (
        Index("ix_workflow_signals_campaign_id", "campaign_id"),
    )


class WorkflowCheckpointRow(Base):
    """One row per campaign storing the coordinator's durable workflow state."""

    __tablename__ = "workflow_checkpoints"

    campaign_id = Column(String, ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True)
    current_stage = Column(String, nullable=False)
    wait_type = Column(String, nullable=True)
    revision_cycle = Column(Integer, nullable=False, default=0)
    resume_token = Column(String, nullable=True)
    context = Column(Text, nullable=False, default="{}")  # JSON text
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class EventOverflowRow(Base):
    """Stores event payloads that exceed the PostgreSQL NOTIFY 8 KB limit.

    When an event payload is too large to send via NOTIFY directly, the full
    payload is written here and NOTIFY carries only the ``overflow_id``
    reference.  The subscriber resolves the reference and broadcasts the full
    payload to WebSocket clients.
    """

    __tablename__ = "event_overflow"

    id = Column(String, primary_key=True)          # UUID
    channel = Column(String, nullable=False)       # channel name (e.g. "workflow_events")
    payload = Column(Text, nullable=False)         # full JSON payload
    created_at = Column(DateTime, nullable=False)


# ---------------------------------------------------------------------------
# Session dependency
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session per request."""
    async with async_session() as session:
        yield session


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Apply Alembic migrations to bring the schema up to date.

    Running migrations (rather than plain create_all) ensures that both
    fresh databases and existing ones that pre-date the owner_id column
    are handled correctly.

    In azure mode the Alembic URL is set to the Azure URL (without an
    embedded password); ``migrations/env.py`` acquires a fresh Entra token
    per connection at runtime.
    """
    import asyncio
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(
        os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "migrations"))
    ))

    if _get_auth_mode() == _DB_AUTH_MODE_AZURE:
        # migrations/env.py will acquire the Entra token per connection.
        alembic_cfg.set_main_option("sqlalchemy.url", _build_azure_db_url())
    else:
        alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL.replace("+asyncpg", ""))

    # Alembic's command.upgrade is synchronous — run it in a thread executor
    # so we don't block the event loop.
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: command.upgrade(alembic_cfg, "head"))


async def close_db() -> None:
    """Dispose of the connection pool and close the Entra credential if open."""
    global _entra_credential
    try:
        await engine.dispose()
    finally:
        if _entra_credential is not None:
            try:
                await _entra_credential.close()
            finally:
                _entra_credential = None
