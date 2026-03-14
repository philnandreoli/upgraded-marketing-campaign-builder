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

from backend.services.database import Base, UserRow, WorkspaceMemberRow, WorkspaceRow
from backend.services.auth import _provision_user, validate_token
import backend.infrastructure.auth as _auth_module


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
        """Calling _provision_user twice updates claims but keeps one row."""
        await _provision_user(db_session, "user-001", "a@example.com", "Alice")
        await _provision_user(db_session, "user-001", "b@example.com", "Alice Updated")

        # Only one row should exist, but claims should be updated.
        count_result = await db_session.execute(
            select(func.count()).select_from(UserRow)
        )
        assert count_result.scalar_one() == 1

        user = await db_session.get(UserRow, "user-001")
        assert user.email == "b@example.com"  # updated from latest JWT claims
        assert user.display_name == "Alice Updated"

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

    async def test_provision_returns_userrow(self, db_session):
        """_provision_user returns the UserRow for the provisioned user."""
        from backend.services.database import UserRow as UR

        row = await _provision_user(db_session, "user-ret", "ret@example.com", "Return Test")
        assert isinstance(row, UR)
        assert row.id == "user-ret"
        assert row.email == "ret@example.com"
        assert row.display_name == "Return Test"
        assert row.role == "admin"  # first user → admin

    async def test_provision_returns_existing_userrow(self, db_session):
        """_provision_user returns the existing UserRow with updated claims."""
        await _provision_user(db_session, "user-existing", "a@example.com", "Alice")
        row = await _provision_user(db_session, "user-existing", "b@example.com", "Alice Updated")
        # Returns the row with updated claims from the latest JWT
        assert row.id == "user-existing"
        assert row.email == "b@example.com"

    async def test_new_user_gets_personal_workspace(self, db_session):
        """A personal workspace is created for a new user on first provisioning."""
        from sqlalchemy import select as sa_select

        await _provision_user(db_session, "user-ws", "ws@example.com", "WS User")

        result = await db_session.execute(
            sa_select(WorkspaceRow).where(WorkspaceRow.owner_id == "user-ws")
        )
        workspaces = result.scalars().all()
        assert len(workspaces) == 1
        ws = workspaces[0]
        assert ws.is_personal is True
        assert ws.name == "WS User's Workspace"
        assert ws.owner_id == "user-ws"

    async def test_personal_workspace_name_falls_back_to_email(self, db_session):
        """Workspace name falls back to email when display_name is None."""
        from sqlalchemy import select as sa_select

        await _provision_user(db_session, "user-ndn", "ndn@example.com", None)

        result = await db_session.execute(
            sa_select(WorkspaceRow).where(WorkspaceRow.owner_id == "user-ndn")
        )
        ws = result.scalars().first()
        assert ws is not None
        assert ws.name == "ndn@example.com's Workspace"

    async def test_personal_workspace_name_falls_back_to_default(self, db_session):
        """Workspace name is 'Personal Workspace' when both display_name and email are None."""
        from sqlalchemy import select as sa_select

        await _provision_user(db_session, "user-anon", None, None)

        result = await db_session.execute(
            sa_select(WorkspaceRow).where(WorkspaceRow.owner_id == "user-anon")
        )
        ws = result.scalars().first()
        assert ws is not None
        assert ws.name == "Personal Workspace"

    async def test_user_added_as_creator_of_personal_workspace(self, db_session):
        """The new user is added as CREATOR of their personal workspace."""
        from sqlalchemy import select as sa_select
        from backend.models.workspace import WorkspaceRole

        await _provision_user(db_session, "user-creator", "creator@example.com", "Creator")

        ws_result = await db_session.execute(
            sa_select(WorkspaceRow).where(WorkspaceRow.owner_id == "user-creator")
        )
        ws = ws_result.scalars().first()
        assert ws is not None

        member_result = await db_session.execute(
            sa_select(WorkspaceMemberRow).where(
                WorkspaceMemberRow.workspace_id == ws.id,
                WorkspaceMemberRow.user_id == "user-creator",
            )
        )
        member = member_result.scalars().first()
        assert member is not None
        assert member.role == WorkspaceRole.CREATOR.value

    async def test_no_duplicate_workspace_on_second_login(self, db_session):
        """Subsequent logins do NOT create additional workspaces."""
        from sqlalchemy import select as sa_select

        await _provision_user(db_session, "user-dup", "dup@example.com", "Dup")
        await _provision_user(db_session, "user-dup", "dup@example.com", "Dup Updated")

        result = await db_session.execute(
            sa_select(WorkspaceRow).where(WorkspaceRow.owner_id == "user-dup")
        )
        workspaces = result.scalars().all()
        assert len(workspaces) == 1


# ---------------------------------------------------------------------------
# validate_token — deactivated user check
# ---------------------------------------------------------------------------

class TestValidateTokenDeactivatedUser:
    """validate_token must return HTTP 403 when the user's account is inactive."""

    async def test_deactivated_user_raises_403(self, db_session):
        """A user with is_active=False triggers a 403 Forbidden response."""
        from fastapi import HTTPException

        # Build a fake UserRow with is_active=False to be returned by _provision_user.
        deactivated_row = UserRow(
            id="deactivated-user",
            email="deactivated@example.com",
            display_name="Deactivated",
            role="viewer",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            is_active=False,
        )

        # Mock the signing key lookup so JWT decoding succeeds.
        mock_jwk = MagicMock()
        mock_jwk.key_id = "test-kid"
        mock_jwk.key = MagicMock()
        mock_jwks = MagicMock()
        mock_jwks.keys = [mock_jwk]

        fake_payload = {
            "oid": "deactivated-user",
            "preferred_username": "deactivated@example.com",
            "name": "Deactivated",
        }

        with patch("backend.infrastructure.auth._get_public_keys", new_callable=AsyncMock, return_value=[{"kid": "test-kid"}]), \
             patch("backend.infrastructure.auth.jwt.PyJWKSet.from_dict", return_value=mock_jwks), \
             patch("backend.infrastructure.auth.jwt.get_unverified_header", return_value={"kid": "test-kid"}), \
             patch("backend.infrastructure.auth.jwt.decode", return_value=fake_payload), \
             patch("backend.infrastructure.auth._provision_user", new_callable=AsyncMock, return_value=deactivated_row):

            with pytest.raises(HTTPException) as exc_info:
                await validate_token("fake.jwt.token", db_session)

        assert exc_info.value.status_code == 403
        assert "deactivated" in exc_info.value.detail.lower()

    async def test_active_user_returns_user_object(self, db_session):
        """An active user passes the is_active check and returns a User."""
        from backend.models.user import User

        active_row = UserRow(
            id="active-user",
            email="active@example.com",
            display_name="Active",
            role="viewer",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            is_active=True,
        )

        mock_jwk = MagicMock()
        mock_jwk.key_id = "test-kid"
        mock_jwk.key = MagicMock()
        mock_jwks = MagicMock()
        mock_jwks.keys = [mock_jwk]

        fake_payload = {
            "oid": "active-user",
            "preferred_username": "active@example.com",
            "name": "Active",
        }

        with patch("backend.infrastructure.auth._get_public_keys", new_callable=AsyncMock, return_value=[{"kid": "test-kid"}]), \
             patch("backend.infrastructure.auth.jwt.PyJWKSet.from_dict", return_value=mock_jwks), \
             patch("backend.infrastructure.auth.jwt.get_unverified_header", return_value={"kid": "test-kid"}), \
             patch("backend.infrastructure.auth.jwt.decode", return_value=fake_payload), \
             patch("backend.infrastructure.auth._provision_user", new_callable=AsyncMock, return_value=active_row):

            user = await validate_token("fake.jwt.token", db_session)

        assert isinstance(user, User)
        assert user.id == "active-user"
        assert user.is_active is True


# ---------------------------------------------------------------------------
# JWKS cache fallback — unknown kid triggers forced refresh
# ---------------------------------------------------------------------------

class TestJWKSCacheFallback:
    """Tests for the JWKS cache fallback on an unknown key ID."""

    def _make_user_row(self) -> UserRow:
        return UserRow(
            id="active-user",
            email="active@example.com",
            display_name="Active",
            role="viewer",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            is_active=True,
        )

    def _mock_jwks(self, kid: str):
        """Return a (mock_jwk, mock_jwks_set) pair for the given kid."""
        mock_jwk = MagicMock()
        mock_jwk.key_id = kid
        mock_jwk.key = MagicMock()
        mock_jwks = MagicMock()
        mock_jwks.keys = [mock_jwk]
        return mock_jwk, mock_jwks

    async def test_unknown_kid_triggers_refresh_and_succeeds(self, db_session):
        """When the cached JWKS doesn't contain the token's kid, a single forced
        refresh is performed and validation succeeds with the refreshed keys."""
        from backend.models.user import User

        # Reset cooldown so the refresh is allowed.
        _auth_module._last_forced_refresh = 0.0

        _, mock_jwks_old = self._mock_jwks("old-kid")   # stale cache: wrong kid
        mock_jwk_new, mock_jwks_new = self._mock_jwks("new-kid")  # fresh keys

        # PyJWKSet.from_dict returns the old JWKS on the first call (cache hit),
        # then the new JWKS on the second call (after forced refresh).
        jwkset_side_effects = [mock_jwks_old, mock_jwks_new]

        fake_payload = {
            "oid": "active-user",
            "preferred_username": "active@example.com",
            "name": "Active",
        }

        with patch("backend.infrastructure.auth._get_public_keys", new_callable=AsyncMock, return_value=[{"kid": "old-kid"}]), \
             patch("backend.infrastructure.auth._refresh_jwks_cache", new_callable=AsyncMock, return_value=[{"kid": "new-kid"}]) as mock_refresh, \
             patch("backend.infrastructure.auth.jwt.PyJWKSet.from_dict", side_effect=jwkset_side_effects), \
             patch("backend.infrastructure.auth.jwt.get_unverified_header", return_value={"kid": "new-kid"}), \
             patch("backend.infrastructure.auth.jwt.decode", return_value=fake_payload), \
             patch("backend.infrastructure.auth._provision_user", new_callable=AsyncMock, return_value=self._make_user_row()):

            user = await validate_token("fake.jwt.token", db_session)

        assert isinstance(user, User)
        assert user.id == "active-user"
        mock_refresh.assert_called_once()

    async def test_unknown_kid_with_cooldown_active_raises_401(self, db_session):
        """When the cooldown is active, a forced refresh is NOT attempted and
        a 401 is raised immediately."""
        import time
        from fastapi import HTTPException

        # Set _last_forced_refresh to now so the cooldown is active.
        _auth_module._last_forced_refresh = time.time()

        _, mock_jwks_old = self._mock_jwks("old-kid")

        with patch("backend.infrastructure.auth._get_public_keys", new_callable=AsyncMock, return_value=[{"kid": "old-kid"}]), \
             patch("backend.infrastructure.auth._refresh_jwks_cache", new_callable=AsyncMock) as mock_refresh, \
             patch("backend.infrastructure.auth.jwt.PyJWKSet.from_dict", return_value=mock_jwks_old), \
             patch("backend.infrastructure.auth.jwt.get_unverified_header", return_value={"kid": "new-kid"}):

            with pytest.raises(HTTPException) as exc_info:
                await validate_token("fake.jwt.token", db_session)

        assert exc_info.value.status_code == 401
        mock_refresh.assert_not_called()

    async def test_unknown_kid_refresh_still_fails_raises_401(self, db_session):
        """If the refreshed JWKS still doesn't contain the token's kid, a 401
        is raised (the key genuinely doesn't exist)."""
        from fastapi import HTTPException

        _auth_module._last_forced_refresh = 0.0

        _, mock_jwks_old = self._mock_jwks("old-kid")
        # After refresh, cache still only has 'old-kid' — token's 'new-kid' absent.
        _, mock_jwks_after_refresh = self._mock_jwks("old-kid")

        with patch("backend.infrastructure.auth._get_public_keys", new_callable=AsyncMock, return_value=[{"kid": "old-kid"}]), \
             patch("backend.infrastructure.auth._refresh_jwks_cache", new_callable=AsyncMock, return_value=[{"kid": "old-kid"}]), \
             patch("backend.infrastructure.auth.jwt.PyJWKSet.from_dict", side_effect=[mock_jwks_old, mock_jwks_after_refresh]), \
             patch("backend.infrastructure.auth.jwt.get_unverified_header", return_value={"kid": "new-kid"}):

            with pytest.raises(HTTPException) as exc_info:
                await validate_token("fake.jwt.token", db_session)

        assert exc_info.value.status_code == 401
