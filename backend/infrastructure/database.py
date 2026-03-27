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
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncGenerator, Callable, Coroutine

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, text
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
# Connection pool defaults
# ---------------------------------------------------------------------------

# Applied to both the azure and local create_async_engine() call sites.
_POOL_CONFIG: dict[str, Any] = {
    "pool_size": 10,       # Base number of persistent connections
    "max_overflow": 20,    # Additional connections under burst load (30 total max)
    "pool_pre_ping": True, # Detect stale/broken connections before checkout
    "pool_recycle": 3600,  # Recycle connections older than 1 hour
}

# ---------------------------------------------------------------------------
# Backward-compatible DATABASE_URL
# ---------------------------------------------------------------------------

# Kept as a module-level constant so that legacy imports and shims continue
# to work.  Must not have a hardcoded default — callers that need the URL in
# local mode should go through _require_database_url() which fails fast with
# a clear error if the variable is unset.
DATABASE_URL = os.getenv("DATABASE_URL", "")

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


def _require_database_url() -> str:
    """Return ``DATABASE_URL``, raising :class:`RuntimeError` if it is unset.

    Only called in local auth mode.  Azure mode uses managed-identity tokens
    and does not need ``DATABASE_URL``.
    """
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL environment variable is required when using "
            "local database authentication. Set it in your .env file or "
            "environment. "
            "Example: postgresql+asyncpg://user:pass@host:5432/dbname"
        )
    return DATABASE_URL


def _should_auto_migrate() -> bool:
    """Return True if the API should apply Alembic migrations on startup.

    Reads the ``API_AUTO_MIGRATE`` environment variable.  When not set,
    defaults to ``True`` in local mode (convenience for developers) and
    ``False`` in azure mode (schema changes are owned by the migration job).

    Explicit values take priority over the mode-derived default, allowing
    operators to override the behaviour for testing or exceptional deployments.
    """
    raw = os.getenv("API_AUTO_MIGRATE")
    if raw is not None:
        return raw.strip().lower() in ("true", "1", "yes")
    # Default: auto-migrate in local mode only.
    return _get_auth_mode() != _DB_AUTH_MODE_AZURE


def _build_azure_db_url() -> str:
    """Build the asyncpg SQLAlchemy URL for Azure Database for PostgreSQL."""
    host = os.getenv("AZURE_POSTGRES_HOST")
    database = os.getenv("AZURE_POSTGRES_DATABASE", "campaigns")
    user = os.getenv("AZURE_POSTGRES_USER")

    if not host or not host.strip() or not user or not user.strip():
        raise RuntimeError(
            "Invalid Azure PostgreSQL configuration: AZURE_POSTGRES_HOST and "
            "AZURE_POSTGRES_USER must be set and non-empty when DB_AUTH_MODE=azure."
        )
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
            **_POOL_CONFIG,
            connect_args={
                "password": _fetch_entra_db_token,
                "ssl": "require",
            },
        )

    # Local / default: password-based DATABASE_URL.
    # Validation via _require_database_url() is deferred to first actual use
    # (_make_alembic_config, get_connection_dsn, init_db startup path) so that
    # the module can be imported without DATABASE_URL being set — this allows
    # unit tests that mock the database layer to collect and run normally.
    logger.debug("Database engine: local mode")
    url = DATABASE_URL or "postgresql+asyncpg://localhost/placeholder_unconfigured"
    return create_async_engine(url, echo=False, future=True, **_POOL_CONFIG)


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
    return _require_database_url().replace("postgresql+asyncpg://", "postgresql://")


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

    __table_args__ = (
        Index("ix_workspace_members_user_role", "user_id", "role"),
    )


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
    version = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index("ix_campaigns_workspace_created", "workspace_id", text("created_at DESC")),
        Index("ix_campaigns_workspace_status", "workspace_id", "status"),
    )


class ImageAssetRow(Base):
    __tablename__ = "image_assets"

    id = Column(String, primary_key=True)
    campaign_id = Column(String, ForeignKey("campaigns.id"), nullable=False, index=True)
    content_piece_index = Column(Integer, nullable=False)
    prompt = Column(Text, nullable=False)
    image_url = Column(Text, nullable=True)
    storage_path = Column(Text, nullable=True)
    dimensions = Column(String, nullable=False, default="1024x1024")
    format = Column(String, nullable=False, default="png")
    created_at = Column(DateTime, nullable=False)


class UserRow(Base):
    """Persisted platform user created JIT on first authentication."""

    __tablename__ = "users"

    id = Column(String, primary_key=True)           # OIDC oid/sub
    email = Column(String, nullable=True, index=True)
    display_name = Column(String, nullable=True, index=True)
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

    __table_args__ = (
        Index("ix_campaign_members_user_id", "user_id"),
    )


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


class CampaignEventRow(Base):
    """Persists each pipeline event emitted by the CoordinatorAgent.

    Provides a durable audit trail for all campaign pipeline events so that
    history is available when users navigate to a campaign page, even if they
    were not connected during pipeline execution.
    """

    __tablename__ = "campaign_events"

    id = Column(String, primary_key=True)          # UUID
    campaign_id = Column(
        String, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    event_type = Column(String, nullable=False)    # e.g. "pipeline_started", "stage_completed"
    stage = Column(String, nullable=True)          # e.g. "strategy", "content"
    payload = Column(Text, nullable=False)         # full JSON-serialised event payload
    owner_id = Column(String, nullable=True)       # user who triggered the action
    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_campaign_events_campaign_id", "campaign_id"),
    )


class CampaignCommentRow(Base):
    """Persists a threaded, section-scoped comment on a campaign."""

    __tablename__ = "campaign_comments"

    id = Column(String, primary_key=True)          # UUID
    campaign_id = Column(
        String, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    parent_id = Column(
        String, ForeignKey("campaign_comments.id"), nullable=True
    )
    section = Column(String, nullable=False)       # e.g. "strategy", "content", "channel_plan"
    content_piece_index = Column(Integer, nullable=True)  # for content-specific comments
    body = Column(Text, nullable=False)
    author_id = Column(String, ForeignKey("users.id"), nullable=False)
    is_resolved = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_campaign_comments_campaign_id", "campaign_id"),
        Index("ix_campaign_comments_campaign_section", "campaign_id", "section"),
        Index("ix_campaign_comments_parent_id", "parent_id"),
    )


class UserSettingsRow(Base):
    """Durable per-user settings persisted across sessions and devices."""

    __tablename__ = "user_settings"

    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    ui_theme = Column(String, nullable=False, default="system")
    locale = Column(String, nullable=False, default="en-US")
    timezone = Column(String, nullable=False, default="UTC")
    default_workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=True)
    notification_prefs = Column(JSON, nullable=False, default=dict)
    dashboard_prefs = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


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

def _make_alembic_config():
    """Return an Alembic :class:`~alembic.config.Config` pointed at our ini file."""
    from alembic.config import Config  # noqa: PLC0415

    # backend/infrastructure/database.py → two parents up = backend/
    _backend_dir = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(_backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(_backend_dir / "migrations"))
    if _get_auth_mode() == _DB_AUTH_MODE_AZURE:
        # migrations/env.py will acquire the Entra token per connection.
        alembic_cfg.set_main_option("sqlalchemy.url", _build_azure_db_url())
    else:
        alembic_cfg.set_main_option("sqlalchemy.url", _require_database_url().replace("+asyncpg", ""))
    return alembic_cfg


async def init_db() -> None:
    """Initialise the database at process startup.

    Behaviour is controlled by the ``API_AUTO_MIGRATE`` environment variable
    (see :func:`_should_auto_migrate`):

    **Auto-migrate** (``API_AUTO_MIGRATE=true``, default in local mode)
        Applies all pending Alembic migrations via ``alembic upgrade head``.
        Preserves local-development convenience — no separate migration step
        is needed.

    **Validate-only** (``API_AUTO_MIGRATE=false``, default in azure mode)
        Schema mutations are owned by the dedicated migration job
        (``backend.apps.migrate.main``) which runs *before* the API and
        worker containers are started.  This function therefore only
        **validates** that the database is already at the expected head
        revision and raises :class:`RuntimeError` if it is not, preventing
        the service from starting with an incompatible schema.
    """
    if _should_auto_migrate():
        await _run_migrations()
    else:
        await _verify_schema_at_head()


async def _run_migrations() -> None:
    """Apply Alembic migrations synchronously in a thread executor.

    Used in ``local`` mode only.  In azure mode schema changes are applied
    by the dedicated migration job; use :func:`_verify_schema_at_head`
    instead.
    """
    import asyncio  # noqa: PLC0415
    from alembic import command  # noqa: PLC0415

    alembic_cfg = _make_alembic_config()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: command.upgrade(alembic_cfg, "head"))


async def _verify_schema_at_head() -> None:
    """Verify the database schema is already at the expected head revision.

    This is called by :func:`init_db` in ``azure`` mode.  It queries the
    ``alembic_version`` table and compares the recorded revision against
    the head revision declared in the migration scripts.

    Raises :class:`RuntimeError` if the schema is behind (or ahead of) the
    expected revision, which prevents the service from starting with an
    incompatible database schema.
    """
    from alembic.script import ScriptDirectory  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    alembic_cfg = _make_alembic_config()
    script = ScriptDirectory.from_config(alembic_cfg)
    expected_head = script.get_current_head()

    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
            row = result.fetchone()
            current_rev = row[0] if row else None
    except Exception as exc:
        raise RuntimeError(
            "Unable to read schema version from the database. "
            "Ensure the migration job has completed successfully before starting this service."
        ) from exc

    if current_rev != expected_head:
        raise RuntimeError(
            f"Database schema mismatch: current revision is {current_rev!r} but the "
            f"application expects {expected_head!r}. "
            "Run the migration job before starting this service."
        )
    logger.info("Schema validation passed (revision=%s)", current_rev)


async def check_schema_compatibility() -> None:
    """Verify the database schema is at the expected Alembic head revision.

    Unlike :func:`init_db`, this function **never** applies migrations — it
    only reads the current schema version and raises :class:`RuntimeError` if
    the recorded revision does not match the application's expected head.

    Intended for use by process entry-points (e.g. the worker) that must
    validate prerequisites without mutating shared infrastructure.  The API
    startup path and the dedicated migration job remain responsible for
    applying schema changes.

    Raises :class:`RuntimeError` if the database is unreachable or the schema
    revision does not match the expected head.
    """
    await _verify_schema_at_head()


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
