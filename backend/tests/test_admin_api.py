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
    roles=[UserRole.ADMIN],
)

_BUILDER_USER = User(
    id="builder-001",
    email="builder@example.com",
    display_name="Builder User",
    roles=[UserRole.CAMPAIGN_BUILDER],
)

_VIEWER_USER = User(
    id="viewer-001",
    email="viewer@example.com",
    display_name="Viewer User",
    roles=[UserRole.VIEWER],
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
        patch("backend.apps.api.startup.init_db", new_callable=AsyncMock),
        patch("backend.apps.api.startup.close_db", new_callable=AsyncMock),
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
            patch("backend.apps.api.startup.init_db", new_callable=AsyncMock),
            patch("backend.apps.api.startup.close_db", new_callable=AsyncMock),
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
        assert data["roles"] == ["admin"]
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

        r = await client.patch("/api/admin/users/u1/role", json={"roles": ["campaign_builder"]})
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "u1"
        assert data["roles"] == ["campaign_builder"]

    async def test_returns_404_for_unknown_user(self, admin_client):
        client, _ = admin_client
        r = await client.patch("/api/admin/users/nobody/role", json={"roles": ["viewer"]})
        assert r.status_code == 404

    async def test_returns_422_for_invalid_role(self, admin_client, db_session):
        client, _ = admin_client
        db_session.add(_make_user_row("u1"))
        await db_session.commit()

        r = await client.patch("/api/admin/users/u1/role", json={"roles": ["superuser"]})
        assert r.status_code == 422

    async def test_prevents_demoting_last_admin(self, admin_client, db_session):
        client, _ = admin_client
        db_session.add(_make_user_row("u1", role="admin"))
        await db_session.commit()

        r = await client.patch("/api/admin/users/u1/role", json={"roles": ["viewer"]})
        assert r.status_code == 409
        assert "last admin" in r.json()["detail"].lower()

    async def test_allows_promoting_viewer_to_admin(self, admin_client, db_session):
        client, _ = admin_client
        db_session.add(_make_user_row("u1", role="viewer"))
        await db_session.commit()

        r = await client.patch("/api/admin/users/u1/role", json={"roles": ["admin"]})
        assert r.status_code == 200
        assert r.json()["roles"] == ["admin"]

    async def test_allows_demoting_admin_when_another_admin_exists(self, admin_client, db_session):
        client, _ = admin_client
        db_session.add(_make_user_row("u1", role="admin"))
        db_session.add(_make_user_row("u2", role="admin"))
        await db_session.commit()

        r = await client.patch("/api/admin/users/u1/role", json={"roles": ["viewer"]})
        assert r.status_code == 200
        assert r.json()["roles"] == ["viewer"]

    async def test_allows_admin_and_campaign_builder_together(self, admin_client, db_session):
        """A user can be both admin and campaign_builder."""
        client, _ = admin_client
        db_session.add(_make_user_row("u1", role="viewer"))
        await db_session.commit()

        r = await client.patch("/api/admin/users/u1/role", json={"roles": ["admin", "campaign_builder"]})
        assert r.status_code == 200
        assert set(r.json()["roles"]) == {"admin", "campaign_builder"}

    async def test_rejects_campaign_builder_and_viewer_together(self, admin_client, db_session):
        """A user cannot be both campaign_builder and viewer."""
        client, _ = admin_client
        db_session.add(_make_user_row("u1", role="viewer"))
        await db_session.commit()

        r = await client.patch("/api/admin/users/u1/role", json={"roles": ["campaign_builder", "viewer"]})
        assert r.status_code == 422
        assert "campaign_builder" in r.json()["detail"].lower()


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

    async def test_response_includes_workspace_id_when_assigned(self, admin_client):
        """workspace_id is present and non-null when campaign belongs to a workspace."""
        client, fresh_store = admin_client
        ws = await fresh_store.create_workspace("Test WS", owner_id="u1")
        await fresh_store.create(CampaignBrief(product_or_service="P1", goal="G1"), owner_id="u1", workspace_id=ws.id)

        r = await client.get("/api/admin/campaigns")
        assert r.status_code == 200
        data = r.json()
        assert data[0]["workspace_id"] == ws.id

    async def test_response_includes_workspace_object_when_assigned(self, admin_client):
        """workspace object with id/name/is_personal is returned for assigned campaigns."""
        client, fresh_store = admin_client
        ws = await fresh_store.create_workspace("My Workspace", owner_id="u1")
        await fresh_store.create(CampaignBrief(product_or_service="P1", goal="G1"), owner_id="u1", workspace_id=ws.id)

        r = await client.get("/api/admin/campaigns")
        assert r.status_code == 200
        data = r.json()
        workspace = data[0]["workspace"]
        assert workspace is not None
        assert workspace["id"] == ws.id
        assert workspace["name"] == "My Workspace"
        assert "is_personal" in workspace

    async def test_response_workspace_id_is_null_for_orphaned_campaigns(self, admin_client):
        """workspace_id is null and workspace is null for orphaned campaigns."""
        client, fresh_store = admin_client
        await fresh_store.create(CampaignBrief(product_or_service="P1", goal="G1"), owner_id="u1")

        r = await client.get("/api/admin/campaigns")
        assert r.status_code == 200
        data = r.json()
        assert data[0]["workspace_id"] is None
        assert data[0]["workspace"] is None

    async def test_returns_403_for_non_admin(self, db_engine):
        """Non-admin cannot list all campaigns."""
        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        async def override_get_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_current_user] = lambda: _VIEWER_USER
        app.dependency_overrides[get_db] = override_get_db

        with (
            patch("backend.apps.api.startup.init_db", new_callable=AsyncMock),
            patch("backend.apps.api.startup.close_db", new_callable=AsyncMock),
        ):
            transport = ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.get("/api/admin/campaigns")
        assert r.status_code == 403

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# GET /api/admin/entra/users
# ---------------------------------------------------------------------------


class TestSearchEntraDirectory:
    async def test_returns_501_when_graph_not_configured(self, admin_client):
        """Returns 501 when AZURE_CLIENT_SECRET is not set."""
        client, _ = admin_client
        r = await client.get("/api/admin/entra/users?search=alice")
        assert r.status_code == 501
        assert "not configured" in r.json()["detail"].lower()

    async def test_returns_empty_list_when_search_is_blank(self, admin_client):
        """Returns empty list when the search term is blank."""
        client, _ = admin_client
        from unittest.mock import MagicMock
        from backend.config import OIDCSettings, Settings

        mock_settings = MagicMock(spec=Settings)
        mock_settings.oidc = MagicMock(spec=OIDCSettings)
        mock_settings.oidc.graph_client_secret = "secret"
        mock_settings.oidc.authority = "https://login.microsoftonline.com/tenant-id/v2.0"
        mock_settings.oidc.client_id = "client-id"

        with patch("backend.api.admin.get_settings", return_value=mock_settings):
            r = await client.get("/api/admin/entra/users?search=  ")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_entra_users_excluding_existing(self, admin_client, db_session):
        """Returns Entra users filtered to exclude those already in the local DB."""
        client, _ = admin_client
        # Pre-provision one of the Entra users in the local DB
        db_session.add(_make_user_row("entra-already-exists", email="existing@example.com"))
        await db_session.commit()

        from unittest.mock import MagicMock
        from backend.config import OIDCSettings, Settings

        mock_settings = MagicMock(spec=Settings)
        mock_settings.oidc = MagicMock(spec=OIDCSettings)
        mock_settings.oidc.graph_client_secret = "secret"
        mock_settings.oidc.authority = "https://login.microsoftonline.com/tenant-id/v2.0"
        mock_settings.oidc.client_id = "client-id"

        entra_results = [
            {"id": "entra-already-exists", "displayName": "Alice", "mail": "existing@example.com", "userPrincipalName": "existing@example.com"},
            {"id": "entra-new-user", "displayName": "Bob", "mail": "bob@example.com", "userPrincipalName": "bob@example.com"},
        ]

        with (
            patch("backend.api.admin.get_settings", return_value=mock_settings),
            patch("backend.api.admin.search_entra_users", new=AsyncMock(return_value=entra_results)),
        ):
            r = await client.get("/api/admin/entra/users?search=b")

        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["id"] == "entra-new-user"
        assert data[0]["display_name"] == "Bob"

    async def test_returns_502_when_graph_api_fails(self, admin_client):
        """Returns 502 when the Graph API call raises an exception."""
        client, _ = admin_client

        from unittest.mock import MagicMock
        from backend.config import OIDCSettings, Settings

        mock_settings = MagicMock(spec=Settings)
        mock_settings.oidc = MagicMock(spec=OIDCSettings)
        mock_settings.oidc.graph_client_secret = "secret"
        mock_settings.oidc.authority = "https://login.microsoftonline.com/tenant-id/v2.0"
        mock_settings.oidc.client_id = "client-id"

        with (
            patch("backend.api.admin.get_settings", return_value=mock_settings),
            patch("backend.api.admin.search_entra_users", new=AsyncMock(side_effect=Exception("network error"))),
        ):
            r = await client.get("/api/admin/entra/users?search=alice")

        assert r.status_code == 502

    async def test_returns_400_for_invalid_characters(self, admin_client):
        """Returns 400 when the search term contains invalid OData characters."""
        client, _ = admin_client
        from unittest.mock import MagicMock
        from backend.config import OIDCSettings, Settings

        mock_settings = MagicMock(spec=Settings)
        mock_settings.oidc = MagicMock(spec=OIDCSettings)
        mock_settings.oidc.graph_client_secret = "secret"
        mock_settings.oidc.authority = "https://login.microsoftonline.com/tenant-id/v2.0"
        mock_settings.oidc.client_id = "client-id"

        with patch("backend.api.admin.get_settings", return_value=mock_settings):
            r = await client.get("/api/admin/entra/users?search=alice%27%29%3Bselect+1--")
        assert r.status_code == 400
        assert "invalid characters" in r.json()["detail"].lower()

    async def test_returns_empty_list_for_overlong_search(self, admin_client):
        """Returns empty list when the search term exceeds the maximum length."""
        client, _ = admin_client
        from unittest.mock import MagicMock
        from backend.config import OIDCSettings, Settings

        mock_settings = MagicMock(spec=Settings)
        mock_settings.oidc = MagicMock(spec=OIDCSettings)
        mock_settings.oidc.graph_client_secret = "secret"
        mock_settings.oidc.authority = "https://login.microsoftonline.com/tenant-id/v2.0"
        mock_settings.oidc.client_id = "client-id"

        overlong_search = "a" * 101
        with patch("backend.api.admin.get_settings", return_value=mock_settings):
            r = await client.get(f"/api/admin/entra/users?search={overlong_search}")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_403_for_non_admin(self, db_engine):
        """Non-admin users cannot search Entra directory."""
        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        async def override_get_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_current_user] = lambda: _VIEWER_USER
        app.dependency_overrides[get_db] = override_get_db

        with (
            patch("backend.apps.api.startup.init_db", new_callable=AsyncMock),
            patch("backend.apps.api.startup.close_db", new_callable=AsyncMock),
        ):
            transport = ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.get("/api/admin/entra/users?search=alice")
        assert r.status_code == 403

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# POST /api/admin/users
# ---------------------------------------------------------------------------


class TestProvisionUser:
    async def test_provisions_user_successfully(self, admin_client, db_session):
        """Admin can pre-provision a new user with a specific role."""
        client, _ = admin_client
        r = await client.post(
            "/api/admin/users",
            json={
                "entra_id": "entra-abc-123",
                "email": "alice@example.com",
                "display_name": "Alice",
                "roles": ["campaign_builder"],
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["id"] == "entra-abc-123"
        assert data["email"] == "alice@example.com"
        assert data["display_name"] == "Alice"
        assert data["roles"] == ["campaign_builder"]
        assert data["is_active"] is True

    async def test_provisions_user_with_admin_role(self, admin_client, db_session):
        """Admin can provision a user with admin role."""
        client, _ = admin_client
        r = await client.post(
            "/api/admin/users",
            json={
                "entra_id": "entra-admin-user",
                "email": "admin2@example.com",
                "display_name": "Second Admin",
                "roles": ["admin"],
            },
        )
        assert r.status_code == 201
        assert r.json()["roles"] == ["admin"]

    async def test_defaults_to_viewer_role(self, admin_client):
        """Provisioned user defaults to viewer role if roles not specified."""
        client, _ = admin_client
        r = await client.post(
            "/api/admin/users",
            json={
                "entra_id": "entra-viewer-user",
                "email": "viewer@example.com",
                "display_name": "Viewer User",
            },
        )
        assert r.status_code == 201
        assert r.json()["roles"] == ["viewer"]

    async def test_returns_409_when_user_already_exists(self, admin_client, db_session):
        """Returns 409 if a user with that Entra ID already exists."""
        client, _ = admin_client
        db_session.add(_make_user_row("entra-dup", email="dup@example.com"))
        await db_session.commit()

        r = await client.post(
            "/api/admin/users",
            json={"entra_id": "entra-dup", "email": "dup@example.com", "roles": ["viewer"]},
        )
        assert r.status_code == 409
        assert "already exists" in r.json()["detail"].lower()

    async def test_returns_422_for_invalid_role(self, admin_client):
        """Returns 422 when an invalid role string is supplied."""
        client, _ = admin_client
        r = await client.post(
            "/api/admin/users",
            json={"entra_id": "entra-xyz", "roles": ["superuser"]},
        )
        assert r.status_code == 422

    async def test_returns_422_for_conflicting_roles(self, admin_client):
        """Returns 422 when campaign_builder and viewer are both specified."""
        client, _ = admin_client
        r = await client.post(
            "/api/admin/users",
            json={"entra_id": "entra-xyz", "roles": ["campaign_builder", "viewer"]},
        )
        assert r.status_code == 422

    async def test_persists_user_in_database(self, admin_client, db_session):
        """The provisioned user is persisted in the database."""
        client, _ = admin_client
        r = await client.post(
            "/api/admin/users",
            json={
                "entra_id": "entra-persist",
                "email": "persist@example.com",
                "display_name": "Persist Test",
                "roles": ["viewer"],
            },
        )
        assert r.status_code == 201

        row = await db_session.get(UserRow, "entra-persist")
        await db_session.refresh(row)
        assert row is not None
        assert row.email == "persist@example.com"
        assert row.is_active is True

    async def test_returns_403_for_non_admin(self, db_engine):
        """Non-admin users cannot provision users."""
        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        async def override_get_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_current_user] = lambda: _VIEWER_USER
        app.dependency_overrides[get_db] = override_get_db

        with (
            patch("backend.apps.api.startup.init_db", new_callable=AsyncMock),
            patch("backend.apps.api.startup.close_db", new_callable=AsyncMock),
        ):
            transport = ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/api/admin/users",
                    json={"entra_id": "xyz", "roles": ["viewer"]},
                )
        assert r.status_code == 403

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
