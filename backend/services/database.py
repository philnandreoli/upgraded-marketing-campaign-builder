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
    """Create tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose of the connection pool."""
    await engine.dispose()
