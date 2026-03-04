"""
Tests for the admin REST API routes.

Uses httpx.AsyncClient with ASGITransport for async HTTP testing.
An in-memory SQLite database (with StaticPool) replaces PostgreSQL so
no database instance is required.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.models.campaign import Campaign, CampaignBrief
from backend.models.user import User, UserRole
from backend.services.auth import get_current_user
from backend.services.database import Base, CampaignMemberRow, UserRow, get_db
from backend.tests.mock_store import InMemoryCampaignStore

_ADMIN_USER = User(
    id="admin-001",
    email="admin@example.com",
    display_name="Admin User",
    role=UserRole.ADMIN,
)

_BUILDER_USER = User(
    id="builder-001",
    email="builder@example.com",
    display_name="Builder User",
    role=UserRole.CAMPAIGN_BUILDER,
)

_VIEWER_USER = User(
    id="viewer-001",
    email="viewer@example.com",
    display_name="Viewer User",
    role=UserRole.VIEWER,
)


def _make_user_row(
    user_id: str,
    email: str = "user@example.com",
    display_name: str = "User",
    role: str = "viewer",
    is_active: bool = True,
) -> UserRow:
    now = datetime.utcnow()
    return UserRow(
        id=user_id,
        email=email,
        display_name=display_name,
        role=role,
        created_at=now,
        updated_at=now,
        is_active=is_active,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_engine():
    """In-memory SQLite engine shared across all sessions via StaticPool."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """A session for pre-populating the test database."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def admin_client(db_engine):
    """
    httpx.AsyncClient pointed at the FastAPI app with:
      - get_current_user → admin user
      - get_db           → in-memory SQLite session
      - get_campaign_store → InMemoryCampaignStore
    """
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    fresh_store = InMemoryCampaignStore()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
    app.dependency_overrides[get_db] = override_get_db

    with (
        patch("backend.api.admin.get_campaign_store", return_value=fresh_store),
        patch("backend.main.init_db", new_callable=AsyncMock),
        patch("backend.main.close_db", new_callable=AsyncMock),
    ):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, fresh_store

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# GET /api/admin/users
# ---------------------------------------------------------------------------


class TestListUsers:
    async def test_returns_empty_list_when_no_users(self, admin_client):
        client, _ = admin_client
        r = await client.get("/api/admin/users")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_all_users(self, admin_client, db_session):
        client, _ = admin_client
        db_session.add(_make_user_row("u1", email="a@example.com", display_name="Alice"))
        db_session.add(_make_user_row("u2", email="b@example.com", display_name="Bob"))
        await db_session.commit()

        r = await client.get("/api/admin/users")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        ids = {item["id"] for item in data}
        assert ids == {"u1", "u2"}

    async def test_search_filters_by_email(self, admin_client, db_session):
        client, _ = admin_client
        db_session.add(_make_user_row("u1", email="alice@example.com", display_name="Alice"))
        db_session.add(_make_user_row("u2", email="bob@example.com", display_name="Bob"))
        await db_session.commit()

        r = await client.get("/api/admin/users?search=alice")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["id"] == "u1"

    async def test_search_filters_by_display_name(self, admin_client, db_session):
        client, _ = admin_client
        db_session.add(_make_user_row("u1", email="a@example.com", display_name="Alice Smith"))
        db_session.add(_make_user_row("u2", email="b@example.com", display_name="Bob Jones"))
        await db_session.commit()

        r = await client.get("/api/admin/users?search=bob")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["id"] == "u2"

    async def test_search_returns_empty_when_no_match(self, admin_client, db_session):
        client, _ = admin_client
        db_session.add(_make_user_row("u1", email="alice@example.com", display_name="Alice"))
        await db_session.commit()

        r = await client.get("/api/admin/users?search=notfound")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_403_for_non_admin(self, db_engine):
        """Non-admin users cannot access the users list."""
        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        async def override_get_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_current_user] = lambda: _BUILDER_USER
        app.dependency_overrides[get_db] = override_get_db

        with (
            patch("backend.main.init_db", new_callable=AsyncMock),
            patch("backend.main.close_db", new_callable=AsyncMock),
        ):
            transport = ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.get("/api/admin/users")
        assert r.status_code == 403

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# GET /api/admin/users/{user_id}
# ---------------------------------------------------------------------------


class TestGetUser:
    async def test_returns_user_detail(self, admin_client, db_session):
        client, _ = admin_client
        db_session.add(_make_user_row("u1", email="alice@example.com", display_name="Alice", role="admin"))
        await db_session.commit()

        r = await client.get("/api/admin/users/u1")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "u1"
        assert data["email"] == "alice@example.com"
        assert data["role"] == "admin"
        assert data["campaign_memberships"] == []

    async def test_returns_404_for_unknown_user(self, admin_client):
        client, _ = admin_client
        r = await client.get("/api/admin/users/does-not-exist")
        assert r.status_code == 404

    async def test_includes_campaign_memberships(self, admin_client, db_session):
        client, _ = admin_client
        now = datetime.utcnow()
        db_session.add(_make_user_row("u1", email="alice@example.com"))
        # CampaignMemberRow — FK to campaigns not enforced by SQLite default
        db_session.add(
            CampaignMemberRow(
                campaign_id="camp-1",
                user_id="u1",
                role="owner",
                added_at=now,
            )
        )
        await db_session.commit()

        r = await client.get("/api/admin/users/u1")
        assert r.status_code == 200
        data = r.json()
        assert len(data["campaign_memberships"]) == 1
        assert data["campaign_memberships"][0]["campaign_id"] == "camp-1"
        assert data["campaign_memberships"][0]["role"] == "owner"


# ---------------------------------------------------------------------------
# PATCH /api/admin/users/{user_id}/role
# ---------------------------------------------------------------------------


class TestUpdateUserRole:
    async def test_updates_role_successfully(self, admin_client, db_session):
        client, _ = admin_client
        # Add two admins so we can demote one.
        db_session.add(_make_user_row("u1", role="admin"))
        db_session.add(_make_user_row("u2", role="admin"))
        await db_session.commit()

        r = await client.patch("/api/admin/users/u1/role", json={"role": "campaign_builder"})
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "u1"
        assert data["role"] == "campaign_builder"

    async def test_returns_404_for_unknown_user(self, admin_client):
        client, _ = admin_client
        r = await client.patch("/api/admin/users/nobody/role", json={"role": "viewer"})
        assert r.status_code == 404

    async def test_returns_422_for_invalid_role(self, admin_client, db_session):
        client, _ = admin_client
        db_session.add(_make_user_row("u1"))
        await db_session.commit()

        r = await client.patch("/api/admin/users/u1/role", json={"role": "superuser"})
        assert r.status_code == 422

    async def test_prevents_demoting_last_admin(self, admin_client, db_session):
        client, _ = admin_client
        db_session.add(_make_user_row("u1", role="admin"))
        await db_session.commit()

        r = await client.patch("/api/admin/users/u1/role", json={"role": "viewer"})
        assert r.status_code == 409
        assert "last admin" in r.json()["detail"].lower()

    async def test_allows_promoting_viewer_to_admin(self, admin_client, db_session):
        client, _ = admin_client
        db_session.add(_make_user_row("u1", role="viewer"))
        await db_session.commit()

        r = await client.patch("/api/admin/users/u1/role", json={"role": "admin"})
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    async def test_allows_demoting_admin_when_another_admin_exists(self, admin_client, db_session):
        client, _ = admin_client
        db_session.add(_make_user_row("u1", role="admin"))
        db_session.add(_make_user_row("u2", role="admin"))
        await db_session.commit()

        r = await client.patch("/api/admin/users/u1/role", json={"role": "viewer"})
        assert r.status_code == 200
        assert r.json()["role"] == "viewer"


# ---------------------------------------------------------------------------
# DELETE /api/admin/users/{user_id}
# ---------------------------------------------------------------------------


class TestDeactivateUser:
    async def test_deactivates_user(self, admin_client, db_session):
        client, _ = admin_client
        db_session.add(_make_user_row("u1"))
        await db_session.commit()

        r = await client.delete("/api/admin/users/u1")
        assert r.status_code == 204

        # Verify user is now inactive
        user = await db_session.get(UserRow, "u1")
        await db_session.refresh(user)
        assert user.is_active is False

    async def test_returns_404_for_unknown_user(self, admin_client):
        client, _ = admin_client
        r = await client.delete("/api/admin/users/nobody")
        assert r.status_code == 404

    async def test_removes_campaign_memberships(self, admin_client, db_session):
        client, _ = admin_client
        now = datetime.utcnow()
        db_session.add(_make_user_row("u1"))
        db_session.add(
            CampaignMemberRow(campaign_id="camp-1", user_id="u1", role="owner", added_at=now)
        )
        db_session.add(
            CampaignMemberRow(campaign_id="camp-2", user_id="u1", role="viewer", added_at=now)
        )
        await db_session.commit()

        r = await client.delete("/api/admin/users/u1")
        assert r.status_code == 204

        # Verify memberships are gone
        from sqlalchemy import select
        result = await db_session.execute(
            select(CampaignMemberRow).where(CampaignMemberRow.user_id == "u1")
        )
        assert result.scalars().all() == []


# ---------------------------------------------------------------------------
# GET /api/admin/campaigns
# ---------------------------------------------------------------------------


class TestListAllCampaigns:
    async def test_returns_empty_list_when_no_campaigns(self, admin_client):
        client, _ = admin_client
        r = await client.get("/api/admin/campaigns")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_all_campaigns(self, admin_client):
        client, fresh_store = admin_client
        c1 = await fresh_store.create(CampaignBrief(product_or_service="P1", goal="G1"), owner_id="u1")
        c2 = await fresh_store.create(CampaignBrief(product_or_service="P2", goal="G2"), owner_id="u2")

        r = await client.get("/api/admin/campaigns")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        ids = {item["id"] for item in data}
        assert ids == {c1.id, c2.id}

    async def test_response_includes_owner_id(self, admin_client):
        client, fresh_store = admin_client
        await fresh_store.create(CampaignBrief(product_or_service="P1", goal="G1"), owner_id="owner-x")

        r = await client.get("/api/admin/campaigns")
        assert r.status_code == 200
        data = r.json()
        assert data[0]["owner_id"] == "owner-x"

    async def test_returns_403_for_non_admin(self, db_engine):
        """Non-admin cannot list all campaigns."""
        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        async def override_get_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_current_user] = lambda: _VIEWER_USER
        app.dependency_overrides[get_db] = override_get_db

        with (
            patch("backend.main.init_db", new_callable=AsyncMock),
            patch("backend.main.close_db", new_callable=AsyncMock),
        ):
            transport = ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.get("/api/admin/campaigns")
        assert r.status_code == 403

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
