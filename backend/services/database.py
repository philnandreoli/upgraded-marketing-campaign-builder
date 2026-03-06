"""
SQLAlchemy async engine & session factory for PostgreSQL.

The DATABASE_URL is read from the environment (set in docker-compose.yml).
"""

from __future__ import annotations

import os

from typing import AsyncGenerator

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/campaigns",
)

engine = create_async_engine(DATABASE_URL, echo=False, future=True)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Declarative base & table
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class CampaignRow(Base):
    """Single-table design: indexed id/status + full document in JSONB."""

    __tablename__ = "campaigns"

    id = Column(String, primary_key=True)
    owner_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, index=True)
    data = Column(Text, nullable=False)  # JSON text of the full Campaign
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


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
    """
    import asyncio
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(
        os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "migrations"))
    ))
    alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL.replace("+asyncpg", ""))

    # Alembic's command.upgrade is synchronous — run it in a thread executor
    # so we don't block the event loop.
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: command.upgrade(alembic_cfg, "head"))


async def close_db() -> None:
    """Dispose of the connection pool."""
    await engine.dispose()
