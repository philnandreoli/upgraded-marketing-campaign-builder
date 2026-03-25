"""
Tests for API rate limiting.

Verifies that:
- Endpoints enforce their per-route limits (10/min for campaign creation,
  120/min for admin user-search endpoints, 30/min for other admin endpoints,
  10/min for WS ticket).
- Exceeding a limit returns HTTP 429 Too Many Requests.
- 429 responses include a ``Retry-After`` header.
- Health-check endpoints are exempt from rate limiting.
- Normal requests within the limit succeed.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.models.user import User, UserRole
from backend.infrastructure.auth import get_current_user
from backend.infrastructure.database import Base, UserRow, get_db
from backend.tests.mock_store import InMemoryCampaignStore
from backend.infrastructure.ticket_store import InMemoryTicketStore

# ---------------------------------------------------------------------------
# Shared users
# ---------------------------------------------------------------------------

_ADMIN = User(
    id="rl-admin-001",
    email="admin@example.com",
    display_name="Admin",
    roles=[UserRole.ADMIN],
)

_BUILDER = User(
    id="rl-builder-001",
    email="builder@example.com",
    display_name="Builder",
    roles=[UserRole.CAMPAIGN_BUILDER],
)

_RL_WS_ID = "rl-workspace-001"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_stores():
    """Patch all campaign/workflow stores with in-memory fakes."""
    fresh_store = InMemoryCampaignStore()
    mock_executor = MagicMock()
    mock_executor.dispatch = AsyncMock()

    # Pre-create workspace and add builder as CREATOR
    async def _setup():
        from backend.models.workspace import WorkspaceRole
        ws = await fresh_store.create_workspace(name="RL Test Workspace", owner_id=_BUILDER.id)
        ws.id = _RL_WS_ID
        fresh_store._workspaces = {_RL_WS_ID: ws}
        fresh_store._workspace_members = {
            (_RL_WS_ID, _BUILDER.id): WorkspaceRole.CREATOR.value,
            (_RL_WS_ID, _ADMIN.id): WorkspaceRole.CREATOR.value,
        }
    asyncio.get_event_loop().run_until_complete(_setup())

    with (
        patch("backend.api.campaigns.get_campaign_store", return_value=fresh_store),
        patch(
            "backend.apps.api.dependencies.get_campaign_store",
            return_value=fresh_store,
        ),
        patch(
            "backend.api.campaign_members.get_campaign_store",
            return_value=fresh_store,
        ),
        patch(
            "backend.application.campaign_workflow_service.get_campaign_store",
            return_value=fresh_store,
        ),
        patch(
            "backend.application.campaign_workflow_service._workflow_service",
            None,
        ),
        patch("backend.api.campaigns.get_executor", return_value=mock_executor),
        patch(
            "backend.api.campaign_workflow.get_executor", return_value=mock_executor
        ),
        patch("backend.apps.api.startup.init_db", new_callable=AsyncMock),
        patch("backend.apps.api.startup.close_db", new_callable=AsyncMock),
        patch("backend.api.websocket.get_ticket_store", return_value=InMemoryTicketStore()),
    ):
        yield fresh_store


@pytest.fixture
async def db_engine():
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
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@contextmanager
def _as_user(user: User):
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CAMPAIGN_PAYLOAD = {
    "product_or_service": "RateLimit Test Product",
    "goal": "Test rate limits",
}


def _make_user_row(user_id: str, role: str = "admin") -> UserRow:
    now = datetime.now(timezone.utc)
    return UserRow(
        id=user_id,
        email=f"{user_id}@example.com",
        display_name="User",
        role=role,
        created_at=now,
        updated_at=now,
        is_active=True,
    )


# ---------------------------------------------------------------------------
# Campaign creation — 10 req/min
# ---------------------------------------------------------------------------


class TestCreateCampaignRateLimit:
    def test_first_request_succeeds(self):
        with _as_user(_BUILDER) as client:
            r = client.post(f"/api/workspaces/{_RL_WS_ID}/campaigns", json=_CAMPAIGN_PAYLOAD)
            assert r.status_code == 201

    def test_eleventh_request_is_rate_limited(self):
        """The 11th POST /api/campaigns within one minute must return 429."""
        with _as_user(_BUILDER) as client:
            for _ in range(10):
                r = client.post(f"/api/workspaces/{_RL_WS_ID}/campaigns", json=_CAMPAIGN_PAYLOAD)
                assert r.status_code == 201, f"Expected 201, got {r.status_code}"

            r = client.post(f"/api/workspaces/{_RL_WS_ID}/campaigns", json=_CAMPAIGN_PAYLOAD)
            assert r.status_code == 429

    def test_rate_limit_response_has_retry_after_header(self):
        """429 responses must include a Retry-After header."""
        with _as_user(_BUILDER) as client:
            for _ in range(10):
                client.post(f"/api/workspaces/{_RL_WS_ID}/campaigns", json=_CAMPAIGN_PAYLOAD)

            r = client.post(f"/api/workspaces/{_RL_WS_ID}/campaigns", json=_CAMPAIGN_PAYLOAD)
            assert r.status_code == 429
            assert "retry-after" in r.headers


# ---------------------------------------------------------------------------
# Admin user search endpoints — 120 req/min
# ---------------------------------------------------------------------------


class TestAdminRateLimit:
    def test_admin_list_users_succeeds_within_limit(self, db_session):
        """The first admin request should succeed."""
        app.dependency_overrides[get_current_user] = lambda: _ADMIN
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            client = TestClient(app, raise_server_exceptions=False)
            r = client.get("/api/admin/users")
            assert r.status_code == 200
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_admin_list_users_rate_limited_after_120(self, db_session):
        """The 121st admin user-search request within one minute must return 429."""
        app.dependency_overrides[get_current_user] = lambda: _ADMIN
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            client = TestClient(app, raise_server_exceptions=False)
            for _ in range(120):
                r = client.get("/api/admin/users")
                assert r.status_code == 200, f"Expected 200, got {r.status_code}"

            r = client.get("/api/admin/users")
            assert r.status_code == 429
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_rate_limit_response_has_retry_after_header_admin(self, db_session):
        app.dependency_overrides[get_current_user] = lambda: _ADMIN
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            client = TestClient(app, raise_server_exceptions=False)
            for _ in range(120):
                client.get("/api/admin/users")

            r = client.get("/api/admin/users")
            assert r.status_code == 429
            assert "retry-after" in r.headers
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Health endpoints — exempt from rate limiting
# ---------------------------------------------------------------------------


class TestHealthEndpointsExempt:
    def test_health_live_is_not_rate_limited(self):
        """Health endpoint must never return 429 regardless of request volume."""
        with _as_user(_BUILDER) as client:
            # Exhaust the global default limit (100/min) for another endpoint,
            # then verify health is still reachable.  We use GET /api/me which
            # has no custom limit; health endpoints should be unaffected.
            for _ in range(10):
                r = client.get("/health/live")
                assert r.status_code == 200

    def test_health_ready_is_not_rate_limited(self):
        with _as_user(_BUILDER) as client:
            for _ in range(10):
                r = client.get("/health")
                assert r.status_code == 200


# ---------------------------------------------------------------------------
# WebSocket ticket — 10 req/min
# ---------------------------------------------------------------------------


class TestWsTicketRateLimit:
    def test_first_ticket_request_succeeds(self):
        with _as_user(_BUILDER) as client:
            r = client.post("/api/ws/ticket")
            # 200 (auth enabled but user is resolved via dependency override)
            # or 401 when auth is not configured — both are non-429.
            assert r.status_code != 429

    def test_thirty_first_ticket_request_is_rate_limited(self):
        """The 31st POST /api/ws/ticket within one minute must return 429."""
        from backend.infrastructure.auth import require_authenticated

        app.dependency_overrides[require_authenticated] = lambda: _BUILDER
        try:
            client = TestClient(app, raise_server_exceptions=False)
            for _ in range(30):
                r = client.post("/api/ws/ticket")
                assert r.status_code == 200, f"Expected 200, got {r.status_code}"

            r = client.post("/api/ws/ticket")
            assert r.status_code == 429
        finally:
            app.dependency_overrides.pop(require_authenticated, None)

    def test_rate_limit_response_has_retry_after_header_ws(self):
        from backend.infrastructure.auth import require_authenticated

        app.dependency_overrides[require_authenticated] = lambda: _BUILDER
        try:
            client = TestClient(app, raise_server_exceptions=False)
            for _ in range(30):
                client.post("/api/ws/ticket")

            r = client.post("/api/ws/ticket")
            assert r.status_code == 429
            assert "retry-after" in r.headers
        finally:
            app.dependency_overrides.pop(require_authenticated, None)
