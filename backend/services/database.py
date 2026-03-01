"""
SQLAlchemy async engine & session factory for PostgreSQL.

The DATABASE_URL is read from the environment (set in docker-compose.yml).
"""

from __future__ import annotations

import os

from sqlalchemy import Column, DateTime, String, Text, text
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
