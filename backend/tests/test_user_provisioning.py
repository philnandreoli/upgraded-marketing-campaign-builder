"""
Tests for JIT user provisioning logic in backend/services/auth.py.

Uses an in-memory SQLite database so no PostgreSQL instance is required.
"""

from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.services.database import Base, UserRow
from backend.services.auth import _provision_user


# ---------------------------------------------------------------------------
# In-memory async SQLite engine for testing (no Postgres required)
# ---------------------------------------------------------------------------

_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_session():
    """Yield a fresh AsyncSession backed by an in-memory SQLite database."""
    engine = create_async_engine(_TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestProvisionUser:
    async def test_first_user_becomes_admin(self, db_session):
        """When the users table is empty, the first provisioned user is admin."""
        await _provision_user(db_session, "user-001", "admin@example.com", "Admin User")

        user = await db_session.get(UserRow, "user-001")
        assert user is not None
        assert user.role == "admin"
        assert user.email == "admin@example.com"
        assert user.display_name == "Admin User"
        assert user.is_active is True

    async def test_second_user_becomes_viewer(self, db_session):
        """After the first user, all new users default to viewer."""
        await _provision_user(db_session, "user-001", "admin@example.com", "Admin")
        await _provision_user(db_session, "user-002", "viewer@example.com", "Viewer")

        viewer = await db_session.get(UserRow, "user-002")
        assert viewer is not None
        assert viewer.role == "viewer"

    async def test_idempotent_for_existing_user(self, db_session):
        """Calling _provision_user twice for the same user is a no-op."""
        await _provision_user(db_session, "user-001", "a@example.com", "Alice")
        await _provision_user(db_session, "user-001", "b@example.com", "Alice Updated")

        # Only one row should exist, and it keeps the original data.
        count_result = await db_session.execute(
            select(func.count()).select_from(UserRow)
        )
        assert count_result.scalar_one() == 1

        user = await db_session.get(UserRow, "user-001")
        assert user.email == "a@example.com"  # original value, not overwritten

    async def test_user_with_no_claims(self, db_session):
        """Provisioning works even when email and display_name are None."""
        await _provision_user(db_session, "user-anonymous", None, None)

        user = await db_session.get(UserRow, "user-anonymous")
        assert user is not None
        assert user.email is None
        assert user.display_name is None
        assert user.role == "admin"  # first user → admin

    async def test_created_at_set(self, db_session):
        """created_at and updated_at are populated on creation."""
        before = datetime.utcnow()
        await _provision_user(db_session, "user-ts", "ts@example.com", "TS")
        after = datetime.utcnow()

        user = await db_session.get(UserRow, "user-ts")
        assert before <= user.created_at <= after
        assert before <= user.updated_at <= after
