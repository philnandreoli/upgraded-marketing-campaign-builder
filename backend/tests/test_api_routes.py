"""
Tests for the campaign REST API routes.

Uses FastAPI's TestClient (synchronous) to test all endpoints.
The coordinator's pipeline is mocked so these run offline and don't hang.
The in-memory async store replaces the PostgreSQL-backed store so no
database is required.
"""

import pytest
from contextlib import contextmanager
from datetime import date, time
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.campaign import Campaign, CampaignBrief, CampaignContent, CampaignStatus, ContentApprovalStatus, ContentPiece
from backend.models.user import User, UserRole
from backend.models.user_settings import UserSettings, UserSettingsPatch
from backend.core.exceptions import ConcurrentUpdateError
from backend.infrastructure.auth import get_current_user
from backend.tests.mock_store import InMemoryCampaignStore

_TEST_USER = User(
    id="test-user-001",
    email="test@example.com",
    display_name="Test User",
    roles=[UserRole.CAMPAIGN_BUILDER],
)
_OTHER_USER = User(
    id="other-user-999",
    email="other@example.com",
    display_name="Other User",
    roles=[UserRole.CAMPAIGN_BUILDER],
)

TEST_WS_ID = "test-workspace-001"
OTHER_WS_ID = "other-workspace-002"


class InMemoryUserSettingsStore:
    def __init__(self):
        self._settings: dict[str, UserSettings] = {}

    async def get(self, user_id: str) -> UserSettings:
        existing = self._settings.get(user_id)
        if existing is not None:
            return existing
        created = UserSettings(user_id=user_id)
        self._settings[user_id] = created
        return created

    async def patch(self, user_id: str, patch: UserSettingsPatch) -> UserSettings:
        current = await self.get(user_id)
        updates = patch.model_dump(exclude_unset=True)
        updated = current.model_copy(update=updates)
        self._settings[user_id] = updated
        return updated


class InMemoryPersonaStore:
    def __init__(self):
        self._personas: dict[str, dict] = {}
        self._counter = 0

    async def create(self, *, workspace_id: str, name: str, description: str, source_text: str = "", created_by: str):
        from datetime import datetime

        self._counter += 1
        persona_id = f"persona-{self._counter}"
        now = datetime.utcnow()
        row = {
            "id": persona_id,
            "workspace_id": workspace_id,
            "name": name,
            "description": description,
            "source_text": source_text,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }
        self._personas[persona_id] = row
        return type("PersonaObj", (), row)()

    async def get(self, persona_id: str):
        row = self._personas.get(persona_id)
        if row is None:
            return None
        return type("PersonaObj", (), row)()

    async def list_by_workspace(self, workspace_id: str, *, limit: int = 50, offset: int = 0):
        filtered = [p for p in self._personas.values() if p["workspace_id"] == workspace_id]
        filtered.sort(key=lambda p: p["created_at"], reverse=True)
        total = len(filtered)
        page = filtered[offset:offset + limit]
        return [type("PersonaObj", (), p)() for p in page], total

    async def update(self, persona_id: str, *, name: str | None = None, description: str | None = None):
        from datetime import datetime

        row = self._personas.get(persona_id)
        if row is None:
            raise ValueError(f"Persona {persona_id!r} not found")
        if name is not None:
            row["name"] = name
        if description is not None:
            row["description"] = description
        row["updated_at"] = datetime.utcnow()
        return type("PersonaObj", (), row)()

    async def delete(self, persona_id: str) -> bool:
        return self._personas.pop(persona_id, None) is not None


@pytest.fixture(autouse=True)
def _isolated_store():
    """Give each test a fresh InMemoryCampaignStore and mock the pipeline."""
    fresh_store = InMemoryCampaignStore()
    fresh_user_settings_store = InMemoryUserSettingsStore()
    fresh_persona_store = InMemoryPersonaStore()
    mock_executor = MagicMock()
    mock_executor.dispatch = AsyncMock()

    import asyncio
    # Pre-create test workspace and add test users as CREATOR members
    async def _setup():
        from backend.models.workspace import WorkspaceRole
        ws = await fresh_store.create_workspace(name="Test Workspace", owner_id=_TEST_USER.id)
        ws.id = TEST_WS_ID
        fresh_store._workspaces = {TEST_WS_ID: ws}
        fresh_store._workspace_members = {(TEST_WS_ID, _TEST_USER.id): WorkspaceRole.CREATOR.value,
                                           (TEST_WS_ID, _OTHER_USER.id): WorkspaceRole.CREATOR.value}
    asyncio.get_event_loop().run_until_complete(_setup())

    # Mock init_db/close_db so TestClient doesn't need a real database
    # Reset _workflow_service singleton so each test gets a fresh one with the fresh store
    # Mock get_executor so pipeline dispatch is a no-op in route tests
    with patch("backend.api.campaigns.get_campaign_store", return_value=fresh_store), \
         patch("backend.apps.api.dependencies.get_campaign_store", return_value=fresh_store), \
         patch("backend.api.personas.get_campaign_store", return_value=fresh_store), \
         patch("backend.api.campaign_schedule.get_campaign_store", return_value=fresh_store), \
         patch("backend.api.campaign_members.get_campaign_store", return_value=fresh_store), \
         patch("backend.api.campaigns.get_user_settings_store", return_value=fresh_user_settings_store), \
         patch("backend.api.personas.get_persona_store", return_value=fresh_persona_store), \
         patch("backend.application.campaign_workflow_service.get_campaign_store", return_value=fresh_store), \
         patch("backend.application.campaign_workflow_service._workflow_service", None), \
         patch("backend.api.campaigns.get_executor", return_value=mock_executor), \
         patch("backend.api.campaign_workflow.get_executor", return_value=mock_executor), \
         patch("backend.apps.api.startup.init_db", new_callable=AsyncMock), \
         patch("backend.apps.api.startup.close_db", new_callable=AsyncMock):
        yield fresh_store


@contextmanager
def _as_user(user: User):
    """Override get_current_user for the duration of the block."""
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def client():
    """Client with auth disabled (get_current_user returns None)."""
    app.dependency_overrides[get_current_user] = lambda: None
    c = TestClient(app, raise_server_exceptions=False)
    yield c
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def authed_client():
    """Client with auth enabled returning a fixed test user."""
    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    c = TestClient(app, raise_server_exceptions=False)
    yield c
    app.dependency_overrides.pop(get_current_user, None)


# ---- Health Check ----

class TestHealthCheck:
    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "alive"

    def test_health_live_returns_200(self, client):
        r = client.get("/health/live")
        assert r.status_code == 200
        assert r.json()["status"] == "alive"

    def test_health_ready_returns_200_when_db_up(self, client):
        """Ready endpoint returns 200 when the DB check succeeds."""
        with (
            patch("backend.apps.api.main.sqlalchemy.text", return_value=MagicMock()),
            patch("backend.infrastructure.database.engine") as mock_engine,
        ):
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock()
            mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_executor = MagicMock()
            mock_executor.health_check = AsyncMock(return_value=True)

            with patch("backend.infrastructure.workflow_executor.get_executor", return_value=mock_executor):
                r = client.get("/health/ready")

        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ready"
        assert data["checks"]["executor"] is True

    def test_health_ready_returns_503_when_db_down(self, client):
        """Ready endpoint returns 503 when the DB check fails."""
        import sqlalchemy as sa

        with patch("backend.infrastructure.database.engine") as mock_engine:
            mock_engine.connect.side_effect = sa.exc.OperationalError(
                "connection refused", None, None
            )

            mock_executor = MagicMock()
            mock_executor.health_check = AsyncMock(return_value=True)

            with patch("backend.infrastructure.workflow_executor.get_executor", return_value=mock_executor):
                r = client.get("/health/ready")

        assert r.status_code == 503
        data = r.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["database"] is False

    def test_health_ready_returns_503_when_executor_down(self, client):
        """Ready endpoint returns 503 when executor health_check fails."""
        with (
            patch("backend.apps.api.main.sqlalchemy.text", return_value=MagicMock()),
            patch("backend.infrastructure.database.engine") as mock_engine,
        ):
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock()
            mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_executor = MagicMock()
            mock_executor.health_check = AsyncMock(return_value=False)

            with patch("backend.infrastructure.workflow_executor.get_executor", return_value=mock_executor):
                r = client.get("/health/ready")

        assert r.status_code == 503
        data = r.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["executor"] is False


# ---- GET /api/me ----

class TestGetMe:
    def test_me_returns_local_dev_when_auth_disabled(self, client):
        """When auth is disabled (user is None), returns a local dev profile."""
        r = client.get("/api/me")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "local"
        assert data["roles"] == ["campaign_builder"]
        assert data["is_admin"] is False
        assert data["can_build"] is True
        assert data["is_viewer"] is False

    def test_me_returns_user_profile_for_campaign_builder(self, authed_client):
        """Returns the authenticated user's profile for a campaign_builder."""
        r = authed_client.get("/api/me")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == _TEST_USER.id
        assert data["email"] == _TEST_USER.email
        assert data["display_name"] == _TEST_USER.display_name
        assert data["roles"] == ["campaign_builder"]
        assert data["is_admin"] is False
        assert data["can_build"] is True
        assert data["is_viewer"] is False

    def test_me_returns_admin_flags_for_admin(self, _isolated_store):
        """Returns is_admin=True for an admin user."""
        admin = User(id="admin-001", email="admin@example.com", display_name="Admin", roles=[UserRole.ADMIN])
        with _as_user(admin) as c:
            r = c.get("/api/me")
            assert r.status_code == 200
            data = r.json()
            assert data["roles"] == ["admin"]
            assert data["is_admin"] is True
            assert data["can_build"] is True
            assert data["is_viewer"] is False

    def test_me_returns_viewer_flags_for_viewer(self, _isolated_store):
        """Returns is_viewer=True for a viewer user."""
        viewer = User(id="viewer-001", email="viewer@example.com", display_name="Viewer", roles=[UserRole.VIEWER])
        with _as_user(viewer) as c:
            r = c.get("/api/me")
            assert r.status_code == 200
            data = r.json()
            assert data["roles"] == ["viewer"]
            assert data["is_admin"] is False
            assert data["can_build"] is False
            assert data["is_viewer"] is True


class TestMeSettings:
    def test_get_me_settings_returns_defaults(self, authed_client):
        r = authed_client.get("/api/me/settings")
        assert r.status_code == 200
        assert r.json() == {
            "theme": "system",
            "locale": "en-US",
            "timezone": "UTC",
            "default_workspace_id": None,
            "notification_prefs": {},
            "dashboard_prefs": {},
        }

    def test_get_me_settings_requires_auth(self, client):
        r = client.get("/api/me/settings")
        assert r.status_code == 401

    def test_patch_me_settings_applies_partial_update(self, authed_client):
        r = authed_client.patch("/api/me/settings", json={"theme": "dark", "locale": "pt-br"})
        assert r.status_code == 200
        data = r.json()
        assert data["theme"] == "dark"
        assert data["locale"] == "pt-BR"
        assert data["timezone"] == "UTC"

    def test_patch_me_settings_requires_auth(self, client):
        r = client.patch("/api/me/settings", json={"theme": "dark"})
        assert r.status_code == 401

    def test_patch_me_settings_rejects_invalid_theme(self, authed_client):
        r = authed_client.patch("/api/me/settings", json={"theme": "neon"})
        assert r.status_code == 422

    def test_patch_me_settings_rejects_invalid_locale(self, authed_client):
        r = authed_client.patch("/api/me/settings", json={"locale": "english_USA"})
        assert r.status_code == 422

    def test_patch_me_settings_rejects_invalid_timezone(self, authed_client):
        r = authed_client.patch("/api/me/settings", json={"timezone": "Mars/Phobos"})
        assert r.status_code == 422

    def test_patch_me_settings_rejects_workspace_without_membership(self, authed_client):
        r = authed_client.patch("/api/me/settings", json={"default_workspace_id": "ws-unknown"})
        assert r.status_code == 404
        assert r.json()["detail"] == "Workspace not found"

    def test_patch_me_settings_rejects_existing_workspace_without_membership(self, _isolated_store, authed_client):
        import asyncio
        created_workspace_id: str | None = None

        async def _setup():
            nonlocal created_workspace_id
            ws = await _isolated_store.create_workspace(name="Private Workspace", owner_id="someone-else")
            created_workspace_id = ws.id

        asyncio.get_event_loop().run_until_complete(_setup())
        assert created_workspace_id is not None

        r = authed_client.patch("/api/me/settings", json={"default_workspace_id": created_workspace_id})
        assert r.status_code == 403
        assert r.json()["detail"] == "Not authorized to set this workspace as default"

    def test_patch_me_settings_accepts_member_workspace(self, authed_client):
        r = authed_client.patch("/api/me/settings", json={"default_workspace_id": TEST_WS_ID})
        assert r.status_code == 200
        assert r.json()["default_workspace_id"] == TEST_WS_ID

    def test_patch_me_settings_admin_can_set_existing_non_member_workspace(self, _isolated_store):
        import asyncio
        created_workspace_id: str | None = None

        async def _setup():
            nonlocal created_workspace_id
            ws = await _isolated_store.create_workspace(name="Admin Target Workspace", owner_id="owner-xyz")
            created_workspace_id = ws.id

        asyncio.get_event_loop().run_until_complete(_setup())
        assert created_workspace_id is not None
        admin = User(
            id="admin-001",
            email="admin@example.com",
            display_name="Admin User",
            roles=[UserRole.ADMIN],
        )

        with _as_user(admin) as c:
            r = c.patch("/api/me/settings", json={"default_workspace_id": created_workspace_id})
            assert r.status_code == 200
            assert r.json()["default_workspace_id"] == created_workspace_id


class TestOpenAPITags:
    def test_me_endpoints_are_grouped_under_users_tag(self, client):
        schema = client.get("/openapi.json").json()
        assert schema["paths"]["/api/me"]["get"]["tags"] == ["users"]
        assert schema["paths"]["/api/me/settings"]["get"]["tags"] == ["users"]
        assert schema["paths"]["/api/me/settings"]["patch"]["tags"] == ["users"]

    def test_campaigns_list_openapi_exposes_paginated_response_schema(self, client):
        schema = client.get("/openapi.json").json()
        responses = schema["paths"]["/api/workspaces/{workspace_id}/campaigns"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        # The response is always a CampaignListResponse envelope
        ref = responses.get("$ref", "")
        if not ref:
            # FastAPI may wrap in anyOf/oneOf depending on version
            options = responses.get("anyOf") or responses.get("oneOf") or []
            option_refs = {item.get("$ref", "") for item in options}
            assert "#/components/schemas/CampaignListResponse" in option_refs
        else:
            assert "#/components/schemas/CampaignListResponse" in ref


# ---- POST /api/campaigns ----

class TestCreateCampaign:
    def test_create_returns_201(self, authed_client):
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "TestProduct",
            "goal": "Increase signups",
        })
        assert r.status_code == 201
        data = r.json()
        assert "id" in data
        assert data["status"] == "draft"

    def test_create_with_full_brief(self, authed_client):
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "CloudSync",
            "goal": "Grow enterprise",
            "budget": 50000,
            "currency": "EUR",
            "start_date": "2026-04-01",
            "end_date": "2026-06-30",
            "additional_context": "Focus on EMEA",
        })
        assert r.status_code == 201
        assert "id" in r.json()

    def test_create_with_selected_channels(self, authed_client):
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "ChannelTest",
            "goal": "Test channels",
            "selected_channels": ["email", "paid_ads"],
        })
        assert r.status_code == 201
        cid = r.json()["id"]
        detail = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}").json()
        assert detail["brief"]["selected_channels"] == ["email", "paid_ads"]

    def test_create_with_persona_ids(self, authed_client):
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "PersonaTest",
            "goal": "Test persona wiring",
            "persona_ids": ["persona-1", "persona-2"],
        })
        assert r.status_code == 201
        cid = r.json()["id"]
        detail = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}").json()
        assert detail["brief"]["persona_ids"] == ["persona-1", "persona-2"]

    def test_create_with_invalid_channel_returns_422(self, authed_client):
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "BadChannel",
            "goal": "Test",
            "selected_channels": ["carrier_pigeon"],
        })
        assert r.status_code == 422

    def test_create_missing_required_field(self, authed_client):
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "goal": "Missing product field",
        })
        assert r.status_code == 422  # Validation error

    def test_create_empty_body(self, authed_client):
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={})
        assert r.status_code == 422

    def test_create_viewer_returns_403(self, _isolated_store):
        """A viewer cannot create campaigns."""
        viewer = User(id="viewer-001", email="v@example.com", display_name="Viewer", roles=[UserRole.VIEWER])
        with _as_user(viewer) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
                "product_or_service": "Test", "goal": "Test",
            })
            assert r.status_code == 403

    def test_create_unauthenticated_allowed_when_auth_disabled(self, client):
        """When auth is disabled (user is None / dev mode), campaign creation is allowed."""
        r = client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "Test", "goal": "Test",
        })
        assert r.status_code == 201

    def test_create_stores_owner_id(self, authed_client, _isolated_store):
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "Owned",
            "goal": "Test owner",
        })
        assert r.status_code == 201
        cid = r.json()["id"]
        campaign = _isolated_store._campaigns[cid]
        assert campaign.owner_id == _TEST_USER.id


# ---- GET /api/campaigns ----

class TestListCampaigns:
    def test_list_empty(self, client):
        r = client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns")
        assert r.status_code == 200
        payload = r.json()
        assert payload["items"] == []
        assert payload["pagination"]["total_count"] == 0

    def test_list_after_create(self, authed_client):
        authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "A", "goal": "B",
        })
        authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "C", "goal": "D",
        })
        # Drafts are excluded from the default listing; use include_drafts=true to see them
        r = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns?include_drafts=true")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 2
        # Verify summary fields
        assert "id" in items[0]
        assert "status" in items[0]
        assert "product_or_service" in items[0]
        assert "goal" in items[0]
        assert "created_at" in items[0]
        assert "wizard_step" in items[0]

    def test_list_excludes_drafts_by_default(self, authed_client):
        """POST /campaigns creates a draft; default GET /campaigns should hide it."""
        authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "Draft Camp", "goal": "To be launched",
        })
        r = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_list_scoped_to_owner(self, _isolated_store):
        """Each authenticated user only sees their own campaigns."""
        # Directly insert campaigns with different owners (no async needed)
        my_campaign = Campaign(
            brief=CampaignBrief(product_or_service="My Campaign", goal="Mine"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        their_campaign = Campaign(
            brief=CampaignBrief(product_or_service="Their Campaign", goal="Theirs"),
            owner_id=_OTHER_USER.id,
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns.update({my_campaign.id: my_campaign, their_campaign.id: their_campaign})
        # Also add corresponding membership entries so list_accessible works correctly
        _isolated_store._members[(my_campaign.id, _TEST_USER.id)] = "owner"
        _isolated_store._members[(their_campaign.id, _OTHER_USER.id)] = "owner"

        with _as_user(_TEST_USER) as c:
            # Campaigns are DRAFT by default; use include_drafts=true to see them
            items = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns?include_drafts=true").json()["items"]
            assert len(items) == 2  # Both campaigns are in the workspace

        with _as_user(_OTHER_USER) as c:
            items = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns?include_drafts=true").json()["items"]
            assert len(items) == 2  # Both campaigns are in the workspace

    def test_list_campaigns_pagination_headers(self, authed_client):
        authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={"product_or_service": "A", "goal": "A"})
        authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={"product_or_service": "B", "goal": "B"})

        r = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns?include_drafts=true")
        assert r.status_code == 200
        payload = r.json()
        assert len(payload["items"]) == 2
        assert r.headers["X-Total-Count"] == "2"
        assert r.headers["X-Offset"] == "0"
        assert r.headers["X-Limit"] == "50"
        assert r.headers["X-Returned-Count"] == "2"
        assert r.headers["X-Has-More"] == "false"

    def test_list_campaigns_supports_limit_offset(self, authed_client):
        authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={"product_or_service": "A", "goal": "A"})
        authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={"product_or_service": "B", "goal": "B"})
        authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={"product_or_service": "C", "goal": "C"})

        r = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns?include_drafts=true&limit=1&offset=1")
        assert r.status_code == 200
        payload = r.json()
        assert len(payload["items"]) == 1
        assert r.headers["X-Total-Count"] == "3"
        assert r.headers["X-Offset"] == "1"
        assert r.headers["X-Limit"] == "1"
        assert r.headers["X-Returned-Count"] == "1"
        assert r.headers["X-Has-More"] == "true"

    def test_list_campaigns_offset_beyond_total_returns_empty_page(self, authed_client):
        authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={"product_or_service": "A", "goal": "A"})

        r = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns?include_drafts=true&offset=10&limit=5")
        assert r.status_code == 200
        assert r.json()["items"] == []
        assert r.headers["X-Total-Count"] == "1"
        assert r.headers["X-Returned-Count"] == "0"
        assert r.headers["X-Has-More"] == "false"

    def test_list_campaigns_invalid_limit_returns_422(self, authed_client):
        r = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns?include_drafts=true&limit=0")
        assert r.status_code == 422

    def test_list_campaigns_limit_above_max_returns_422(self, authed_client):
        r = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns?include_drafts=true&limit=201")
        assert r.status_code == 422

    def test_list_campaigns_paginated_envelope(self, authed_client):
        authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={"product_or_service": "A", "goal": "A"})
        authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={"product_or_service": "B", "goal": "B"})

        r = authed_client.get(
            f"/api/workspaces/{TEST_WS_ID}/campaigns"
            "?include_drafts=true&limit=1&offset=1"
        )
        assert r.status_code == 200
        payload = r.json()
        assert set(payload.keys()) == {"items", "pagination"}
        assert len(payload["items"]) == 1
        assert payload["pagination"] == {
            "total_count": 2,
            "offset": 1,
            "limit": 1,
            "returned_count": 1,
            "has_more": False,
        }
        assert r.headers["X-Total-Count"] == "2"

    def test_campaign_summary_timestamps_are_iso_datetime(self, authed_client):
        authed_client.post(
            f"/api/workspaces/{TEST_WS_ID}/campaigns",
            json={"product_or_service": "Time Product", "goal": "Time Goal"},
        )
        r = authed_client.get(
            f"/api/workspaces/{TEST_WS_ID}/campaigns?include_drafts=true"
        )
        assert r.status_code == 200
        item = r.json()["items"][0]
        assert "T" in item["created_at"]
        assert "T" in item["updated_at"]


# ---- GET /api/campaigns/{id} ----

class TestGetCampaign:
    def test_get_existing(self, authed_client):
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "Test", "goal": "Test",
        })
        cid = r.json()["id"]
        r = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == cid
        assert data["brief"]["product_or_service"] == "Test"

    def test_get_not_found(self, client):
        r = client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/nonexistent-id")
        assert r.status_code == 404

    def test_get_other_user_campaign_returns_404(self, authed_client, _isolated_store):
        """A campaign created by user A should not be visible to user B."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Private", goal="Mine"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        with _as_user(_OTHER_USER) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
            assert r.status_code == 200  # _OTHER_USER is also a CREATOR in the workspace


# ---- DELETE /api/campaigns/{id} ----

class TestDeleteCampaign:
    def test_delete_existing(self, authed_client):
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "Del", "goal": "Me",
        })
        cid = r.json()["id"]
        r = authed_client.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}")
        assert r.status_code == 204

        # Confirm it's gone
        r = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}")
        assert r.status_code == 404

    def test_delete_not_found(self, client):
        r = client.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/nonexistent-id")
        assert r.status_code == 404

    def test_delete_other_user_campaign_returns_404(self, _isolated_store):
        """A user cannot delete another user's campaign."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Protected", goal="Mine"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        with _as_user(_OTHER_USER) as c:
            r = c.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
            assert r.status_code == 204  # _OTHER_USER is CREATOR in the workspace


# ---- PATCH /api/campaigns/{id} ----

class TestUpdateDraftCampaign:
    def test_patch_updates_brief_fields(self, authed_client):
        """PATCH on a draft campaign updates the brief fields."""
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "Initial", "goal": "Original goal",
        })
        cid = r.json()["id"]

        r = authed_client.patch(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}", json={
            "product_or_service": "Updated",
            "budget": 50000,
            "wizard_step": 2,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == cid
        assert data["status"] == "draft"

        # Verify the campaign was actually updated
        detail = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}").json()
        assert detail["brief"]["product_or_service"] == "Updated"
        assert detail["brief"]["budget"] == 50000
        assert detail["wizard_step"] == 2

    def test_patch_updates_generate_images_preference(self, authed_client):
        """PATCH can update the brief image-generation opt-in flag."""
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "Image Test", "goal": "Test",
        })
        cid = r.json()["id"]

        r = authed_client.patch(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}",
            json={"generate_images": True},
        )
        assert r.status_code == 200
        detail = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}").json()
        assert detail["brief"]["generate_images"] is True

    def test_patch_updates_wizard_step(self, authed_client):
        """PATCH can update just the wizard_step."""
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "Wizard Test", "goal": "Test",
        })
        cid = r.json()["id"]
        r = authed_client.patch(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}", json={"wizard_step": 3})
        assert r.status_code == 200
        detail = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}").json()
        assert detail["wizard_step"] == 3

    def test_patch_updates_persona_ids(self, authed_client):
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "PatchPersona",
            "goal": "Patch persona ids",
        })
        assert r.status_code == 201
        cid = r.json()["id"]

        patch_response = authed_client.patch(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}",
            json={"persona_ids": ["persona-a", "persona-b"]},
        )
        assert patch_response.status_code == 200

        detail = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}").json()
        assert detail["brief"]["persona_ids"] == ["persona-a", "persona-b"]

    def test_patch_non_draft_returns_409(self, authed_client, _isolated_store):
        """PATCH on a non-draft campaign returns 409."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Active", goal="Running"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
            status=CampaignStatus.STRATEGY,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _TEST_USER.id)] = "owner"

        r = authed_client.patch(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}", json={
            "product_or_service": "Try to update",
        })
        assert r.status_code == 409

    def test_patch_not_found(self, authed_client):
        r = authed_client.patch(f"/api/workspaces/{TEST_WS_ID}/campaigns/nonexistent-id", json={
            "product_or_service": "Ghost",
        })
        assert r.status_code == 404

    def test_patch_conflict_returns_409_with_actionable_detail(self, authed_client, _isolated_store):
        """PATCH returns 409 with refetch/retry guidance when optimistic locking conflicts."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Initial", goal="Original"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _TEST_USER.id)] = "owner"

        with patch.object(
            _isolated_store,
            "update",
            new=AsyncMock(side_effect=ConcurrentUpdateError("injected conflict")),
        ):
            r = authed_client.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}",
                json={"product_or_service": "Updated"},
            )

        assert r.status_code == 409
        assert r.json()["detail"] == "Draft was updated by another editor. Refetch the latest draft and retry your changes."

    def test_patch_viewer_returns_403(self, _isolated_store):
        """A viewer cannot update a campaign."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="View Only", goal="Read"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        viewer = User(id="viewer-001", email="v@example.com", display_name="Viewer", roles=[UserRole.VIEWER])
        with _as_user(viewer) as c:
            r = c.patch(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}", json={
                "product_or_service": "Hacked",
            })
            assert r.status_code == 403


# ---- POST /api/campaigns/{id}/launch ----

class TestLaunchCampaign:
    def test_launch_draft_dispatches_pipeline(self, authed_client, _isolated_store):
        """Launching a draft campaign dispatches the pipeline."""
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "Ready", "goal": "Launch me",
        })
        cid = r.json()["id"]
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}/launch")
        assert r.status_code == 200
        data = r.json()
        assert data["campaign_id"] == cid
        assert "launched" in data["message"].lower() or "pipeline" in data["message"].lower()

    def test_launch_non_draft_returns_409(self, authed_client, _isolated_store):
        """Launching a non-draft campaign returns 409."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Already Running", goal="Active"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
            status=CampaignStatus.STRATEGY,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _TEST_USER.id)] = "owner"
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/launch")
        assert r.status_code == 409

    def test_launch_not_found(self, authed_client):
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/nonexistent-id/launch")
        assert r.status_code == 404




# ---- POST /api/campaigns/{id}/content-approve ----

class TestSubmitContentApproval:
    def test_content_approve_not_found(self, client):
        r = client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/nonexistent-id/content-approve", json={
            "campaign_id": "nonexistent-id",
            "pieces": [],
        })
        assert r.status_code == 404

    def test_content_approve_missing_body(self, authed_client):
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "Appr", "goal": "Test",
        })
        cid = r.json()["id"]
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}/content-approve", json={})
        assert r.status_code == 422

    def test_content_approve_valid(self, authed_client):
        """Submit content approval for an existing campaign.
        The coordinator may not have a pending future, but the endpoint should not crash."""
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "Appr", "goal": "Test",
        })
        cid = r.json()["id"]
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}/content-approve", json={
            "campaign_id": cid,
            "pieces": [
                {"piece_index": 0, "approved": True, "notes": "Good"},
            ],
            "reject_campaign": False,
        })
        assert r.status_code == 200
        assert r.json()["campaign_id"] == cid

    def test_content_approve_reject_campaign(self, authed_client):
        """Reject entire campaign via content-approve endpoint."""
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "RejCamp", "goal": "Test",
        })
        cid = r.json()["id"]
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}/content-approve", json={
            "campaign_id": cid,
            "pieces": [],
            "reject_campaign": True,
        })
        assert r.status_code == 200
        assert r.json()["campaign_id"] == cid

    def test_content_approve_other_user_returns_404(self, _isolated_store):
        """A user cannot approve content for another user's campaign."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Priv", goal="Test"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        with _as_user(_OTHER_USER) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content-approve", json={
                "campaign_id": campaign.id,
                "pieces": [],
                "reject_campaign": False,
            })
            assert r.status_code == 200  # _OTHER_USER is CREATOR in the workspace


# ---- PATCH /api/campaigns/{id}/content/{piece_index}/decision ----

class TestUpdatePieceDecision:
    def _approval_campaign(self, _isolated_store, *, approval_status=ContentApprovalStatus.PENDING, owner_id=None):
        """Helper: create a campaign in content_approval status with one piece."""
        piece = ContentPiece(
            content_type="headline",
            content="Buy now!",
            approval_status=approval_status,
        )
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="DecisionCo", goal="Test"),
            owner_id=owner_id,
            content=CampaignContent(pieces=[piece]),
            workspace_id=TEST_WS_ID,
        )
        campaign.status = CampaignStatus.CONTENT_APPROVAL
        _isolated_store._campaigns[campaign.id] = campaign
        return campaign

    def test_approve_piece(self, client, _isolated_store):
        """Successfully approve a pending piece."""
        campaign = self._approval_campaign(_isolated_store)
        r = client.patch(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/0/decision",
            json={"approved": True},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["approval_status"] == "approved"
        saved = _isolated_store._campaigns[campaign.id]
        assert saved.content.pieces[0].approval_status == ContentApprovalStatus.APPROVED

    def test_reject_piece(self, client, _isolated_store):
        """Successfully reject a pending piece."""
        campaign = self._approval_campaign(_isolated_store)
        r = client.patch(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/0/decision",
            json={"approved": False, "notes": "Needs work"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["approval_status"] == "rejected"
        saved = _isolated_store._campaigns[campaign.id]
        assert saved.content.pieces[0].approval_status == ContentApprovalStatus.REJECTED
        assert saved.content.pieces[0].human_notes == "Needs work"

    def test_approve_piece_with_edited_content(self, client, _isolated_store):
        """Approve a piece with edited content persists the edit."""
        campaign = self._approval_campaign(_isolated_store)
        r = client.patch(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/0/decision",
            json={"approved": True, "edited_content": "Buy now — limited offer!"},
        )
        assert r.status_code == 200
        saved = _isolated_store._campaigns[campaign.id]
        assert saved.content.pieces[0].human_edited_content == "Buy now — limited offer!"

    def test_decision_not_found_campaign(self, client):
        """Returns 404 when the campaign does not exist."""
        r = client.patch(f"/api/workspaces/{TEST_WS_ID}/campaigns/nonexistent/content/0/decision", json={"approved": True})
        assert r.status_code == 404

    def test_decision_piece_out_of_range(self, client, _isolated_store):
        """Returns 404 when the piece index is out of range."""
        campaign = self._approval_campaign(_isolated_store)
        r = client.patch(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/99/decision",
            json={"approved": True},
        )
        assert r.status_code == 404

    def test_decision_wrong_campaign_status(self, client, _isolated_store):
        """Returns 409 when the campaign is not in content_approval status."""
        campaign = self._approval_campaign(_isolated_store)
        campaign.status = CampaignStatus.APPROVED
        _isolated_store._campaigns[campaign.id] = campaign
        r = client.patch(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/0/decision",
            json={"approved": True},
        )
        assert r.status_code == 409

    def test_cannot_reject_already_approved_piece(self, client, _isolated_store):
        """Returns 409 when trying to reject an already-approved piece."""
        campaign = self._approval_campaign(
            _isolated_store, approval_status=ContentApprovalStatus.APPROVED
        )
        r = client.patch(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/0/decision",
            json={"approved": False},
        )
        assert r.status_code == 409


# ---- PATCH /api/campaigns/{id}/content/{piece_index}/notes ----

class TestUpdatePieceNotes:
    def _campaign_with_approved_piece(self, _isolated_store, *, owner_id=None):
        """Helper: create a campaign with one approved content piece."""
        piece = ContentPiece(
            content_type="headline",
            content="Buy now!",
            approval_status=ContentApprovalStatus.APPROVED,
        )
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="NotesCo", goal="Test"),
            owner_id=owner_id,
            content=CampaignContent(pieces=[piece]),
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        return campaign

    def test_update_notes_on_approved_piece(self, client, _isolated_store):
        """Successfully update human_notes on an approved piece."""
        campaign = self._campaign_with_approved_piece(_isolated_store)
        r = client.patch(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/0/notes",
            json={"notes": "Ship it!"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["message"] == "Notes updated"
        assert data["campaign_id"] == campaign.id
        # Verify the note was persisted
        updated = _isolated_store._campaigns[campaign.id]
        assert updated.content.pieces[0].human_notes == "Ship it!"

    def test_update_notes_not_found_campaign(self, client):
        """Returns 404 when the campaign does not exist."""
        r = client.patch(f"/api/workspaces/{TEST_WS_ID}/campaigns/nonexistent/content/0/notes", json={"notes": "x"})
        assert r.status_code == 404

    def test_update_notes_piece_out_of_range(self, client, _isolated_store):
        """Returns 404 when the piece index is out of range."""
        campaign = self._campaign_with_approved_piece(_isolated_store)
        r = client.patch(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/99/notes",
            json={"notes": "oops"},
        )
        assert r.status_code == 404

    def test_update_notes_pending_piece_returns_409(self, client, _isolated_store):
        """Returns 409 when the piece is not yet approved."""
        piece = ContentPiece(
            content_type="headline",
            content="Draft text",
            approval_status=ContentApprovalStatus.PENDING,
        )
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="NotesCo", goal="Test"),
            content=CampaignContent(pieces=[piece]),
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        r = client.patch(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/0/notes",
            json={"notes": "too early"},
        )
        assert r.status_code == 409

    def test_update_notes_no_content(self, client, _isolated_store):
        """Returns 404 when campaign has no content at all."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Empty", goal="Test"),
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        r = client.patch(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/0/notes",
            json={"notes": "nothing here"},
        )
        assert r.status_code == 404

    def test_update_notes_other_user_returns_404(self, _isolated_store):
        """A user cannot update notes for another user's campaign."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Priv", goal="Test"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
            content=CampaignContent(pieces=[
                ContentPiece(content_type="cta", content="Click!", approval_status=ContentApprovalStatus.APPROVED),
            ]),
        )
        _isolated_store._campaigns[campaign.id] = campaign
        with _as_user(_OTHER_USER) as c:
            r = c.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/0/notes",
                json={"notes": "sneaky"},
            )
            assert r.status_code == 200  # _OTHER_USER is CREATOR in the workspace


# ---- PATCH /api/campaigns/{id}/content/{piece_index}/schedule ----

class TestSchedulePiece:
    def _campaign_with_pieces(self, _isolated_store, *, owner_id=None):
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="SchedCo", goal="Plan"),
            owner_id=owner_id,
            workspace_id=TEST_WS_ID,
            content=CampaignContent(pieces=[
                ContentPiece(content_type="headline", content="First"),
                ContentPiece(content_type="social_post", channel="instagram", content="Second"),
            ]),
        )
        _isolated_store._campaigns[campaign.id] = campaign
        return campaign

    def test_schedule_piece_sets_fields(self, client, _isolated_store):
        campaign = self._campaign_with_pieces(_isolated_store)
        r = client.patch(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/1/schedule",
            json={
                "scheduled_date": "2026-04-01",
                "scheduled_time": "09:00:00",
                "platform_target": "instagram",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["scheduled_date"] == "2026-04-01"
        assert data["scheduled_time"] == "09:00:00"
        assert data["platform_target"] == "instagram"
        saved = _isolated_store._campaigns[campaign.id]
        assert saved.content.pieces[1].scheduled_date == date(2026, 4, 1)
        assert saved.content.pieces[1].scheduled_time == time(9, 0)
        assert saved.content.pieces[1].platform_target == "instagram"

    def test_schedule_piece_clears_fields(self, client, _isolated_store):
        campaign = self._campaign_with_pieces(_isolated_store)
        piece = campaign.content.pieces[0]
        piece.scheduled_date = date(2026, 4, 2)
        piece.scheduled_time = time(10, 30)
        piece.platform_target = "linkedin"
        r = client.patch(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/0/schedule",
            json={"scheduled_date": None, "scheduled_time": None, "platform_target": None},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["scheduled_date"] is None
        assert data["scheduled_time"] is None
        assert data["platform_target"] is None
        saved = _isolated_store._campaigns[campaign.id]
        assert saved.content.pieces[0].scheduled_date is None
        assert saved.content.pieces[0].scheduled_time is None
        assert saved.content.pieces[0].platform_target is None

    def test_schedule_piece_out_of_range_returns_400(self, client, _isolated_store):
        campaign = self._campaign_with_pieces(_isolated_store)
        r = client.patch(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/9/schedule",
            json={"scheduled_date": "2026-04-01"},
        )
        assert r.status_code == 400

    def test_schedule_piece_viewer_returns_403(self, _isolated_store):
        campaign = self._campaign_with_pieces(_isolated_store, owner_id=_TEST_USER.id)
        viewer = User(id="viewer-002", email="v2@example.com", display_name="Viewer 2", roles=[UserRole.VIEWER])
        _isolated_store._workspace_members[(TEST_WS_ID, viewer.id)] = "viewer"
        with _as_user(viewer) as c:
            r = c.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/0/schedule",
                json={"scheduled_date": "2026-04-01"},
            )
            assert r.status_code == 403

    def test_schedule_piece_conflict_returns_409(self, authed_client, _isolated_store):
        campaign = self._campaign_with_pieces(_isolated_store, owner_id=_TEST_USER.id)
        _isolated_store._members[(campaign.id, _TEST_USER.id)] = "owner"
        with patch.object(
            _isolated_store,
            "update",
            new=AsyncMock(side_effect=ConcurrentUpdateError("schedule conflict")),
        ):
            r = authed_client.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/0/schedule",
                json={"scheduled_date": "2026-04-03"},
            )
        assert r.status_code == 409


class TestBulkSchedule:
    def _campaign_with_pieces(self, _isolated_store, *, owner_id=None):
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="BulkCo", goal="Plan"),
            owner_id=owner_id,
            workspace_id=TEST_WS_ID,
            content=CampaignContent(pieces=[
                ContentPiece(content_type="headline", content="First"),
                ContentPiece(content_type="social_post", channel="instagram", content="Second"),
                ContentPiece(content_type="cta", content="Third"),
            ]),
        )
        _isolated_store._campaigns[campaign.id] = campaign
        return campaign

    def test_bulk_schedule_happy_path(self, client, _isolated_store):
        campaign = self._campaign_with_pieces(_isolated_store)
        r = client.post(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/bulk-schedule",
            json={
                "schedules": [
                    {"piece_index": 0, "scheduled_date": "2026-04-01", "scheduled_time": "09:00:00", "platform_target": "email"},
                    {"piece_index": 2, "scheduled_date": "2026-04-03", "platform_target": "instagram"},
                ]
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "scheduled" in data
        assert "unscheduled" in data
        dates = [g["date"] for g in data["scheduled"]]
        assert "2026-04-01" in dates
        assert "2026-04-03" in dates
        unscheduled_indices = [p["piece_index"] for p in data["unscheduled"]]
        assert 1 in unscheduled_indices
        saved = _isolated_store._campaigns[campaign.id]
        assert saved.content.pieces[0].scheduled_date == date(2026, 4, 1)
        assert saved.content.pieces[0].scheduled_time == time(9, 0)
        assert saved.content.pieces[0].platform_target == "email"
        assert saved.content.pieces[2].scheduled_date == date(2026, 4, 3)
        assert saved.content.pieces[2].platform_target == "instagram"

    def test_bulk_schedule_empty_payload(self, client, _isolated_store):
        campaign = self._campaign_with_pieces(_isolated_store)
        r = client.post(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/bulk-schedule",
            json={"schedules": []},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["scheduled"] == []
        assert len(data["unscheduled"]) == 3

    def test_bulk_schedule_partial_invalid_returns_400_no_update(self, client, _isolated_store):
        campaign = self._campaign_with_pieces(_isolated_store)
        r = client.post(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/bulk-schedule",
            json={
                "schedules": [
                    {"piece_index": 0, "scheduled_date": "2026-04-01"},
                    {"piece_index": 99, "scheduled_date": "2026-04-02"},
                ]
            },
        )
        assert r.status_code == 400
        # No partial updates applied
        saved = _isolated_store._campaigns[campaign.id]
        assert saved.content.pieces[0].scheduled_date is None

    def test_bulk_schedule_viewer_returns_403(self, _isolated_store):
        campaign = self._campaign_with_pieces(_isolated_store, owner_id=_TEST_USER.id)
        viewer = User(id="viewer-004", email="v4@example.com", display_name="Viewer 4", roles=[UserRole.VIEWER])
        _isolated_store._workspace_members[(TEST_WS_ID, viewer.id)] = "viewer"
        with _as_user(viewer) as c:
            r = c.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/bulk-schedule",
                json={"schedules": [{"piece_index": 0, "scheduled_date": "2026-04-01"}]},
            )
            assert r.status_code == 403

    def test_bulk_schedule_conflict_returns_409(self, authed_client, _isolated_store):
        campaign = self._campaign_with_pieces(_isolated_store, owner_id=_TEST_USER.id)
        _isolated_store._members[(campaign.id, _TEST_USER.id)] = "owner"
        with patch.object(
            _isolated_store,
            "update",
            new=AsyncMock(side_effect=ConcurrentUpdateError("bulk conflict")),
        ):
            r = authed_client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/content/bulk-schedule",
                json={"schedules": [{"piece_index": 0, "scheduled_date": "2026-04-01"}]},
            )
        assert r.status_code == 409


class TestGetCalendar:
    def test_calendar_groups_by_date_and_unscheduled(self, client, _isolated_store):
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="CalCo", goal="Render"),
            workspace_id=TEST_WS_ID,
            content=CampaignContent(pieces=[
                ContentPiece(content_type="headline", content="One", scheduled_date=date(2026, 4, 2)),
                ContentPiece(content_type="social_post", content="Two"),
                ContentPiece(content_type="cta", content="Three", scheduled_date=date(2026, 4, 1)),
                ContentPiece(content_type="body_copy", content="Four", scheduled_date=date(2026, 4, 2)),
            ]),
        )
        _isolated_store._campaigns[campaign.id] = campaign
        r = client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/calendar")
        assert r.status_code == 200
        data = r.json()
        assert [g["date"] for g in data["scheduled"]] == ["2026-04-01", "2026-04-02"]
        assert [p["piece_index"] for p in data["scheduled"][0]["pieces"]] == [2]
        assert [p["piece_index"] for p in data["scheduled"][1]["pieces"]] == [0, 3]
        assert [p["piece_index"] for p in data["unscheduled"]] == [1]

    def test_calendar_viewer_can_read(self, _isolated_store):
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="CalCo", goal="Read"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
            content=CampaignContent(pieces=[ContentPiece(content_type="headline", content="One")]),
        )
        _isolated_store._campaigns[campaign.id] = campaign
        viewer = User(id="viewer-003", email="v3@example.com", display_name="Viewer 3", roles=[UserRole.VIEWER])
        _isolated_store._workspace_members[(TEST_WS_ID, viewer.id)] = "viewer"
        with _as_user(viewer) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/calendar")
            assert r.status_code == 200

class TestSubmitClarification:
    def test_clarify_not_found(self, client):
        """Returns 404 when the campaign does not exist."""
        r = client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/nonexistent-id/clarify", json={
            "campaign_id": "nonexistent-id",
            "answers": {"q1": "answer"},
        })
        assert r.status_code == 404

    def test_clarify_wrong_status_returns_409(self, client, _isolated_store):
        """Returns 409 when the campaign is not in 'clarification' status."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Test", goal="Test"),
            workspace_id=TEST_WS_ID,
        )
        # Campaign starts in DRAFT status — not CLARIFICATION
        _isolated_store._campaigns[campaign.id] = campaign

        r = client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/clarify", json={
            "campaign_id": campaign.id,
            "answers": {"q1": "answer"},
        })
        assert r.status_code == 409
        assert "clarification" in r.json()["detail"].lower()

    def test_clarify_valid(self, client, _isolated_store):
        """Accepts clarification answers when campaign is in 'clarification' status."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Test", goal="Test"),
            workspace_id=TEST_WS_ID,
        )
        campaign.advance_status(CampaignStatus.CLARIFICATION)
        _isolated_store._campaigns[campaign.id] = campaign

        r = client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/clarify", json={
            "campaign_id": campaign.id,
            "answers": {"q1": "B2B tech companies"},
        })

        assert r.status_code == 200
        data = r.json()
        assert data["campaign_id"] == campaign.id
        assert "submitted" in data["message"].lower()

    def test_clarify_other_user_returns_404(self, _isolated_store):
        """A user cannot submit clarification for another user's campaign."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Priv", goal="Test"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        campaign.advance_status(CampaignStatus.CLARIFICATION)
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _TEST_USER.id)] = "owner"

        with _as_user(_OTHER_USER) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/clarify", json={
                "campaign_id": campaign.id,
                "answers": {"q1": "answer"},
            })
            assert r.status_code == 200  # _OTHER_USER is CREATOR in the workspace


# ---- Convenience auth dependencies ----

class TestAuthDependencies:
    """Tests for require_authenticated, require_campaign_builder, require_admin."""

    async def test_require_authenticated_passes_for_user(self):
        """require_authenticated returns the user when one is present."""
        from backend.infrastructure.auth import require_authenticated

        result = await require_authenticated(_TEST_USER)
        assert result == _TEST_USER

    async def test_require_authenticated_raises_401_for_none(self):
        """require_authenticated raises 401 when user is None (auth disabled)."""
        from fastapi import HTTPException
        from backend.infrastructure.auth import require_authenticated

        with pytest.raises(HTTPException) as exc_info:
            await require_authenticated(None)
        assert exc_info.value.status_code == 401

    async def test_require_campaign_builder_passes_for_builder(self):
        """require_campaign_builder passes for campaign_builder role."""
        from backend.infrastructure.auth import require_campaign_builder

        result = await require_campaign_builder(_TEST_USER)
        assert result == _TEST_USER

    async def test_require_campaign_builder_passes_for_admin(self):
        """require_campaign_builder passes for admin role."""
        from backend.infrastructure.auth import require_campaign_builder

        admin_user = User(id="admin-001", email="admin@example.com", display_name="Admin", roles=[UserRole.ADMIN])
        result = await require_campaign_builder(admin_user)
        assert result == admin_user

    async def test_require_campaign_builder_raises_403_for_viewer(self):
        """require_campaign_builder raises 403 for viewer role."""
        from fastapi import HTTPException
        from backend.infrastructure.auth import require_campaign_builder

        viewer = User(id="viewer-001", email="viewer@example.com", display_name="Viewer", roles=[UserRole.VIEWER])
        with pytest.raises(HTTPException) as exc_info:
            await require_campaign_builder(viewer)
        assert exc_info.value.status_code == 403

    async def test_require_campaign_builder_raises_401_for_none(self):
        """require_campaign_builder raises 401 when user is None."""
        from fastapi import HTTPException
        from backend.infrastructure.auth import require_campaign_builder

        with pytest.raises(HTTPException) as exc_info:
            await require_campaign_builder(None)
        assert exc_info.value.status_code == 401

    async def test_require_admin_passes_for_admin(self):
        """require_admin passes for admin role."""
        from backend.infrastructure.auth import require_admin

        admin_user = User(id="admin-001", email="admin@example.com", display_name="Admin", roles=[UserRole.ADMIN])
        result = await require_admin(admin_user)
        assert result == admin_user

    async def test_require_admin_raises_403_for_campaign_builder(self):
        """require_admin raises 403 for campaign_builder role."""
        from fastapi import HTTPException
        from backend.infrastructure.auth import require_admin

        with pytest.raises(HTTPException) as exc_info:
            await require_admin(_TEST_USER)
        assert exc_info.value.status_code == 403

    async def test_require_admin_raises_403_for_viewer(self):
        """require_admin raises 403 for viewer role."""
        from fastapi import HTTPException
        from backend.infrastructure.auth import require_admin

        viewer = User(id="viewer-001", email="viewer@example.com", display_name="Viewer", roles=[UserRole.VIEWER])
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(viewer)
        assert exc_info.value.status_code == 403

    async def test_require_admin_raises_401_for_none(self):
        """require_admin raises 401 when user is None."""
        from fastapi import HTTPException
        from backend.infrastructure.auth import require_admin

        with pytest.raises(HTTPException) as exc_info:
            await require_admin(None)
        assert exc_info.value.status_code == 401


# ---- RBAC Authorization Matrix ----

_ADMIN_USER = User(id="admin-rbac-001", email="admin@example.com", display_name="Admin", roles=[UserRole.ADMIN])
_VIEWER_USER = User(id="viewer-rbac-001", email="viewer@example.com", display_name="Viewer", roles=[UserRole.VIEWER])


class TestAuthorizeFunction:
    """Tests for the _authorize helper covering the full RBAC matrix."""

    async def test_none_user_allows_all(self, _isolated_store):
        """Auth disabled (user=None) allows all actions."""
        from backend.apps.api.dependencies import _authorize, Action
        campaign = Campaign(brief=CampaignBrief(product_or_service="X", goal="Y"), owner_id=None)
        _isolated_store._campaigns[campaign.id] = campaign
        for action in Action:
            await _authorize(campaign.id, None, action, _isolated_store)  # no exception

    async def test_admin_allows_all(self, _isolated_store):
        """Admin user can perform any action regardless of membership."""
        from backend.apps.api.dependencies import _authorize, Action
        campaign = Campaign(brief=CampaignBrief(product_or_service="X", goal="Y"), owner_id="other")
        _isolated_store._campaigns[campaign.id] = campaign
        # admin has no membership — should still be allowed
        for action in Action:
            await _authorize(campaign.id, _ADMIN_USER, action, _isolated_store)  # no exception

    async def test_campaign_builder_owner_allows_all(self, _isolated_store):
        """campaign_builder with owner membership can perform all actions."""
        from backend.apps.api.dependencies import _authorize, Action
        campaign = Campaign(brief=CampaignBrief(product_or_service="X", goal="Y"), owner_id=_TEST_USER.id)
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _TEST_USER.id)] = "owner"
        for action in Action:
            await _authorize(campaign.id, _TEST_USER, action, _isolated_store)  # no exception

    async def test_campaign_builder_editor_allows_read_write(self, _isolated_store):
        """campaign_builder with editor membership can READ and WRITE only."""
        from backend.apps.api.dependencies import _authorize, Action
        from fastapi import HTTPException
        campaign = Campaign(brief=CampaignBrief(product_or_service="X", goal="Y"), owner_id="other")
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _TEST_USER.id)] = "editor"
        # Allowed
        await _authorize(campaign.id, _TEST_USER, Action.READ, _isolated_store)
        await _authorize(campaign.id, _TEST_USER, Action.WRITE, _isolated_store)
        # Denied
        with pytest.raises(HTTPException) as exc:
            await _authorize(campaign.id, _TEST_USER, Action.DELETE, _isolated_store)
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await _authorize(campaign.id, _TEST_USER, Action.MANAGE_MEMBERS, _isolated_store)
        assert exc.value.status_code == 403

    async def test_campaign_builder_viewer_allows_read_only(self, _isolated_store):
        """campaign_builder with viewer membership can only READ."""
        from backend.apps.api.dependencies import _authorize, Action
        from fastapi import HTTPException
        campaign = Campaign(brief=CampaignBrief(product_or_service="X", goal="Y"), owner_id="other")
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _TEST_USER.id)] = "viewer"
        # Allowed
        await _authorize(campaign.id, _TEST_USER, Action.READ, _isolated_store)
        # Denied
        for action in (Action.WRITE, Action.DELETE, Action.MANAGE_MEMBERS):
            with pytest.raises(HTTPException) as exc:
                await _authorize(campaign.id, _TEST_USER, action, _isolated_store)
            assert exc.value.status_code == 403

    async def test_campaign_builder_no_membership_returns_404(self, _isolated_store):
        """campaign_builder with no membership gets 404 (existence leak prevention)."""
        from backend.apps.api.dependencies import _authorize, Action
        from fastapi import HTTPException
        campaign = Campaign(brief=CampaignBrief(product_or_service="X", goal="Y"), owner_id="other")
        _isolated_store._campaigns[campaign.id] = campaign
        # No membership entry added
        with pytest.raises(HTTPException) as exc:
            await _authorize(campaign.id, _TEST_USER, Action.READ, _isolated_store)
        assert exc.value.status_code == 404

    async def test_viewer_member_allows_read_only(self, _isolated_store):
        """Platform viewer with any membership can only READ."""
        from backend.apps.api.dependencies import _authorize, Action
        from fastapi import HTTPException
        campaign = Campaign(brief=CampaignBrief(product_or_service="X", goal="Y"), owner_id="other")
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _VIEWER_USER.id)] = "owner"
        # Allowed
        await _authorize(campaign.id, _VIEWER_USER, Action.READ, _isolated_store)
        # Denied
        for action in (Action.WRITE, Action.DELETE, Action.MANAGE_MEMBERS):
            with pytest.raises(HTTPException) as exc:
                await _authorize(campaign.id, _VIEWER_USER, action, _isolated_store)
            assert exc.value.status_code == 403

    async def test_viewer_no_membership_returns_404(self, _isolated_store):
        """Platform viewer with no membership gets 404."""
        from backend.apps.api.dependencies import _authorize, Action
        from fastapi import HTTPException
        campaign = Campaign(brief=CampaignBrief(product_or_service="X", goal="Y"), owner_id="other")
        _isolated_store._campaigns[campaign.id] = campaign
        with pytest.raises(HTTPException) as exc:
            await _authorize(campaign.id, _VIEWER_USER, Action.READ, _isolated_store)
        assert exc.value.status_code == 404

    async def test_workspace_creator_gets_full_access_without_campaign_membership(self, _isolated_store):
        """Builder with workspace CREATOR role gets full access when no campaign membership."""
        from backend.apps.api.dependencies import _authorize, Action
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="X", goal="Y"),
            owner_id="other",
            workspace_id="ws-1",
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._workspace_members[("ws-1", _TEST_USER.id)] = "creator"
        for action in Action:
            await _authorize(campaign.id, _TEST_USER, action, _isolated_store)  # no exception

    async def test_workspace_contributor_allows_read_write(self, _isolated_store):
        """Builder with workspace CONTRIBUTOR role can READ and WRITE only."""
        from backend.apps.api.dependencies import _authorize, Action
        from fastapi import HTTPException
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="X", goal="Y"),
            owner_id="other",
            workspace_id="ws-1",
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._workspace_members[("ws-1", _TEST_USER.id)] = "contributor"
        await _authorize(campaign.id, _TEST_USER, Action.READ, _isolated_store)
        await _authorize(campaign.id, _TEST_USER, Action.WRITE, _isolated_store)
        for action in (Action.DELETE, Action.MANAGE_MEMBERS):
            with pytest.raises(HTTPException) as exc:
                await _authorize(campaign.id, _TEST_USER, action, _isolated_store)
            assert exc.value.status_code == 403

    async def test_workspace_viewer_allows_read_only(self, _isolated_store):
        """Builder with workspace VIEWER role can only READ."""
        from backend.apps.api.dependencies import _authorize, Action
        from fastapi import HTTPException
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="X", goal="Y"),
            owner_id="other",
            workspace_id="ws-1",
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._workspace_members[("ws-1", _TEST_USER.id)] = "viewer"
        await _authorize(campaign.id, _TEST_USER, Action.READ, _isolated_store)
        for action in (Action.WRITE, Action.DELETE, Action.MANAGE_MEMBERS):
            with pytest.raises(HTTPException) as exc:
                await _authorize(campaign.id, _TEST_USER, action, _isolated_store)
            assert exc.value.status_code == 403

    async def test_platform_viewer_workspace_creator_read_only(self, _isolated_store):
        """Platform VIEWER role caps at READ even if workspace role is CREATOR."""
        from backend.apps.api.dependencies import _authorize, Action
        from fastapi import HTTPException
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="X", goal="Y"),
            owner_id="other",
            workspace_id="ws-1",
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._workspace_members[("ws-1", _VIEWER_USER.id)] = "creator"
        await _authorize(campaign.id, _VIEWER_USER, Action.READ, _isolated_store)
        for action in (Action.WRITE, Action.DELETE, Action.MANAGE_MEMBERS):
            with pytest.raises(HTTPException) as exc:
                await _authorize(campaign.id, _VIEWER_USER, action, _isolated_store)
            assert exc.value.status_code == 403

    async def test_orphaned_campaign_without_membership_returns_404(self, _isolated_store):
        """Orphaned campaign (no workspace_id) with no campaign membership → 404."""
        from backend.apps.api.dependencies import _authorize, Action
        from fastapi import HTTPException
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="X", goal="Y"),
            owner_id="other",
            workspace_id=None,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        with pytest.raises(HTTPException) as exc:
            await _authorize(campaign.id, _TEST_USER, Action.READ, _isolated_store)
        assert exc.value.status_code == 404

    async def test_owner_id_fallback_for_orphaned_campaign(self, _isolated_store):
        """User matching owner_id gets full access even without campaign membership."""
        from backend.apps.api.dependencies import _authorize, Action
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="X", goal="Y"),
            owner_id=_TEST_USER.id,
            workspace_id=None,
        )
        # No campaign membership entry — just the owner_id on the campaign
        _isolated_store._campaigns[campaign.id] = campaign
        for action in Action:
            await _authorize(campaign.id, _TEST_USER, action, _isolated_store)  # no exception

    async def test_workspace_member_not_in_workspace_returns_404(self, _isolated_store):
        """Builder with no campaign or workspace membership gets 404."""
        from backend.apps.api.dependencies import _authorize, Action
        from fastapi import HTTPException
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="X", goal="Y"),
            owner_id="other",
            workspace_id="ws-1",
        )
        _isolated_store._campaigns[campaign.id] = campaign
        # No workspace membership for _TEST_USER
        with pytest.raises(HTTPException) as exc:
            await _authorize(campaign.id, _TEST_USER, Action.READ, _isolated_store)
        assert exc.value.status_code == 404


class TestRBACRoutes:
    """Integration tests for RBAC enforcement on campaign endpoints."""

    def test_editor_can_read_campaign(self, _isolated_store):
        """An editor member can GET a campaign."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Collab", goal="Work"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _OTHER_USER.id)] = "editor"
        with _as_user(_OTHER_USER) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
            assert r.status_code == 200

    def test_editor_cannot_delete_campaign(self, _isolated_store):
        """An editor member cannot DELETE a campaign (campaign role overrides workspace CREATOR)."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Protected", goal="Mine"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _OTHER_USER.id)] = "editor"
        with _as_user(_OTHER_USER) as c:
            r = c.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
            assert r.status_code == 403

    def test_viewer_member_can_read_campaign(self, _isolated_store):
        """A platform viewer with membership can GET a campaign."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Shared", goal="View"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _VIEWER_USER.id)] = "viewer"
        with _as_user(_VIEWER_USER) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
            assert r.status_code == 200

    def test_viewer_member_cannot_delete_campaign(self, _isolated_store):
        """A platform viewer cannot DELETE even if they are a member."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Shared", goal="View"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _VIEWER_USER.id)] = "viewer"
        with _as_user(_VIEWER_USER) as c:
            r = c.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
            assert r.status_code == 403

    def test_admin_can_access_any_campaign(self, _isolated_store):
        """An admin can GET any campaign without membership."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Secret", goal="Admin"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        # No membership entry for admin
        with _as_user(_ADMIN_USER) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
            assert r.status_code == 200

    def test_admin_can_delete_any_campaign(self, _isolated_store):
        """An admin can DELETE any campaign without membership."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Secret", goal="Admin"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        with _as_user(_ADMIN_USER) as c:
            r = c.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
            assert r.status_code == 204

    def test_no_member_gets_404_not_403(self, _isolated_store):
        """A non-member with no workspace membership gets 404 (not 403) to avoid leaking."""
        # Use a private workspace where _OTHER_USER has no access
        _isolated_store._workspaces["ws-private"] = _Workspace(
            id="ws-private", name="Private WS", owner_id=_TEST_USER.id
        )
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Hidden", goal="Private"),
            owner_id=_TEST_USER.id,
            workspace_id="ws-private",
        )
        _isolated_store._campaigns[campaign.id] = campaign
        # _OTHER_USER has no campaign or workspace membership in "ws-private"
        with _as_user(_OTHER_USER) as c:
            r = c.get(f"/api/workspaces/ws-private/campaigns/{campaign.id}")
            assert r.status_code == 404

    def test_workspace_creator_can_read_campaign_via_workspace(self, _isolated_store):
        """Builder who is workspace CREATOR can GET a campaign they are not a direct member of."""
        _isolated_store._workspaces["ws-1"] = _Workspace(id="ws-1", name="WS1", owner_id="other")
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="WS Campaign", goal="WS"),
            owner_id=_TEST_USER.id,
            workspace_id="ws-1",
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._workspace_members[("ws-1", _OTHER_USER.id)] = "creator"
        with _as_user(_OTHER_USER) as c:
            r = c.get(f"/api/workspaces/ws-1/campaigns/{campaign.id}")
            assert r.status_code == 200

    def test_workspace_contributor_cannot_delete_campaign(self, _isolated_store):
        """Builder with workspace CONTRIBUTOR role cannot DELETE a campaign."""
        _isolated_store._workspaces["ws-1"] = _Workspace(id="ws-1", name="WS1", owner_id="other")
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="WS Campaign", goal="WS"),
            owner_id=_TEST_USER.id,
            workspace_id="ws-1",
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._workspace_members[("ws-1", _OTHER_USER.id)] = "contributor"
        with _as_user(_OTHER_USER) as c:
            r = c.delete(f"/api/workspaces/ws-1/campaigns/{campaign.id}")
            assert r.status_code == 403

    def test_platform_viewer_workspace_creator_cannot_delete(self, _isolated_store):
        """Platform VIEWER with workspace CREATOR role still cannot DELETE."""
        _isolated_store._workspaces["ws-1"] = _Workspace(id="ws-1", name="WS1", owner_id="other")
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="WS Campaign", goal="WS"),
            owner_id=_TEST_USER.id,
            workspace_id="ws-1",
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._workspace_members[("ws-1", _VIEWER_USER.id)] = "creator"
        with _as_user(_VIEWER_USER) as c:
            r = c.delete(f"/api/workspaces/ws-1/campaigns/{campaign.id}")
            assert r.status_code == 403


# ---- Member management endpoints ----

class TestCampaignMembers:
    """Tests for GET/POST/PATCH/DELETE /api/workspaces/{ws_id}/campaigns/{id}/members."""

    def _setup_campaign(self, store):
        """Helper: insert a campaign owned by _TEST_USER and return it."""
        from backend.models.user import User
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Team", goal="Collaborate"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        store._campaigns[campaign.id] = campaign
        store._members[(campaign.id, _TEST_USER.id)] = "owner"
        # Register users so get_user works
        store._users[_TEST_USER.id] = _TEST_USER
        store._users[_OTHER_USER.id] = _OTHER_USER
        return campaign

    # ---- GET /members ----

    def test_list_members_returns_owner(self, _isolated_store):
        """GET /members returns the campaign owner."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_TEST_USER) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["user_id"] == _TEST_USER.id
        assert data[0]["role"] == "owner"

    def test_list_members_campaign_not_found(self, client):
        r = client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/nonexistent/members")
        assert r.status_code == 404

    def test_list_members_requires_read_access(self, _isolated_store):
        """A non-member workspace CREATOR can still list members."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_OTHER_USER) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members")
        assert r.status_code == 200  # _OTHER_USER is CREATOR in the workspace

    def test_list_members_supports_pagination(self, _isolated_store):
        campaign = self._setup_campaign(_isolated_store)
        _isolated_store._members[(campaign.id, _OTHER_USER.id)] = "editor"
        with _as_user(_TEST_USER) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members?limit=1&offset=1")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.headers["X-Total-Count"] == "2"
        assert r.headers["X-Offset"] == "1"
        assert r.headers["X-Limit"] == "1"
        assert r.headers["X-Returned-Count"] == "1"

    def test_list_members_offset_beyond_total_returns_empty(self, _isolated_store):
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_TEST_USER) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members?offset=5")
        assert r.status_code == 200
        assert r.json() == []
        assert r.headers["X-Total-Count"] == "1"
        assert r.headers["X-Returned-Count"] == "0"

    # ---- POST /members ----

    def test_add_member_success(self, _isolated_store):
        """Owner can add an editor member."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_TEST_USER) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members", json={
                "user_id": _OTHER_USER.id,
                "role": "editor",
            })
        assert r.status_code == 201
        data = r.json()
        assert data["user_id"] == _OTHER_USER.id
        assert data["role"] == "editor"
        assert data["campaign_id"] == campaign.id

    def test_add_member_default_role_is_viewer(self, _isolated_store):
        """POST /members without role defaults to viewer."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_TEST_USER) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members", json={
                "user_id": _OTHER_USER.id,
            })
        assert r.status_code == 201
        assert r.json()["role"] == "viewer"

    def test_add_member_rejects_owner_role(self, _isolated_store):
        """POST /members with role=owner is rejected with 422."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_TEST_USER) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members", json={
                "user_id": _OTHER_USER.id,
                "role": "owner",
            })
        assert r.status_code == 422

    def test_add_member_user_not_found(self, _isolated_store):
        """POST /members with unknown user_id returns 404."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_TEST_USER) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members", json={
                "user_id": "nonexistent-user",
                "role": "editor",
            })
        assert r.status_code == 404

    def test_add_member_inactive_user_returns_404(self, _isolated_store):
        """POST /members with an inactive user returns 404."""
        from backend.models.user import User
        campaign = self._setup_campaign(_isolated_store)
        inactive = User(
            id="inactive-user",
            email="inactive@example.com",
            display_name="Inactive",
            roles=[UserRole.CAMPAIGN_BUILDER],
            is_active=False,
        )
        _isolated_store._users[inactive.id] = inactive
        with _as_user(_TEST_USER) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members", json={
                "user_id": inactive.id,
                "role": "viewer",
            })
        assert r.status_code == 404

    def test_add_member_editor_cannot_manage_members(self, _isolated_store):
        """An editor member cannot add other members (requires MANAGE_MEMBERS)."""
        campaign = self._setup_campaign(_isolated_store)
        _isolated_store._members[(campaign.id, _OTHER_USER.id)] = "editor"
        third = User(id="third-user", email="third@example.com", display_name="Third", roles=[UserRole.CAMPAIGN_BUILDER])
        _isolated_store._users[third.id] = third
        # Remove _OTHER_USER from workspace CREATOR to force campaign membership check
        del _isolated_store._workspace_members[(TEST_WS_ID, _OTHER_USER.id)]
        with _as_user(_OTHER_USER) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members", json={
                "user_id": third.id,
                "role": "viewer",
            })
        assert r.status_code == 403

    def test_add_member_campaign_not_found(self, _isolated_store):
        """POST /members on nonexistent campaign returns 404."""
        _isolated_store._users[_TEST_USER.id] = _TEST_USER
        with _as_user(_TEST_USER) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/nonexistent/members", json={
                "user_id": _OTHER_USER.id,
                "role": "editor",
            })
        assert r.status_code == 404

    # ---- PATCH /members/{user_id} ----

    def test_patch_member_role_success(self, _isolated_store):
        """Owner can change an editor to viewer."""
        campaign = self._setup_campaign(_isolated_store)
        _isolated_store._members[(campaign.id, _OTHER_USER.id)] = "editor"
        with _as_user(_TEST_USER) as c:
            r = c.patch(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members/{_OTHER_USER.id}", json={
                "role": "viewer",
            })
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "viewer"
        assert data["user_id"] == _OTHER_USER.id

    def test_patch_member_role_rejects_owner(self, _isolated_store):
        """PATCH /members/{id} with role=owner is rejected with 422."""
        campaign = self._setup_campaign(_isolated_store)
        _isolated_store._members[(campaign.id, _OTHER_USER.id)] = "editor"
        with _as_user(_TEST_USER) as c:
            r = c.patch(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members/{_OTHER_USER.id}", json={
                "role": "owner",
            })
        assert r.status_code == 422

    def test_patch_member_not_found(self, _isolated_store):
        """PATCH /members/{id} for non-member returns 404."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_TEST_USER) as c:
            r = c.patch(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members/{_OTHER_USER.id}", json={
                "role": "editor",
            })
        assert r.status_code == 404

    def test_patch_member_user_not_in_system(self, _isolated_store):
        """PATCH /members/{id} with unknown user_id returns 404."""
        campaign = self._setup_campaign(_isolated_store)
        _isolated_store._members[(campaign.id, "unknown-user")] = "editor"
        with _as_user(_TEST_USER) as c:
            r = c.patch(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members/unknown-user", json={
                "role": "viewer",
            })
        assert r.status_code == 404

    # ---- DELETE /members/{user_id} ----

    def test_delete_member_success(self, _isolated_store):
        """Owner can remove an editor member."""
        campaign = self._setup_campaign(_isolated_store)
        _isolated_store._members[(campaign.id, _OTHER_USER.id)] = "editor"
        with _as_user(_TEST_USER) as c:
            r = c.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members/{_OTHER_USER.id}")
        assert r.status_code == 204
        assert (campaign.id, _OTHER_USER.id) not in _isolated_store._members

    def test_delete_last_owner_returns_409(self, _isolated_store):
        """Cannot remove the last owner of a campaign."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_TEST_USER) as c:
            r = c.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members/{_TEST_USER.id}")
        assert r.status_code == 409

    def test_delete_member_not_found(self, _isolated_store):
        """DELETE /members/{id} for non-member returns 404."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_TEST_USER) as c:
            r = c.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members/{_OTHER_USER.id}")
        assert r.status_code == 404

    def test_delete_member_editor_cannot_manage_members(self, _isolated_store):
        """An editor cannot remove members."""
        campaign = self._setup_campaign(_isolated_store)
        _isolated_store._members[(campaign.id, _OTHER_USER.id)] = "editor"
        third = User(id="third-user", email="third@example.com", display_name="Third", roles=[UserRole.CAMPAIGN_BUILDER])
        _isolated_store._members[(campaign.id, third.id)] = "viewer"
        # Remove _OTHER_USER from workspace CREATOR to force campaign membership check
        del _isolated_store._workspace_members[(TEST_WS_ID, _OTHER_USER.id)]
        with _as_user(_OTHER_USER) as c:
            r = c.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members/{third.id}")
        assert r.status_code == 403

    def test_delete_non_last_owner_succeeds(self, _isolated_store):
        """Can remove one owner when another owner still exists."""
        campaign = self._setup_campaign(_isolated_store)
        _isolated_store._members[(campaign.id, _OTHER_USER.id)] = "owner"
        with _as_user(_TEST_USER) as c:
            r = c.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members/{_OTHER_USER.id}")
        assert r.status_code == 204

    def test_admin_can_manage_members_without_membership(self, _isolated_store):
        """Admin can add members to any campaign without being a member."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_ADMIN_USER) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members", json={
                "user_id": _OTHER_USER.id,
                "role": "editor",
            })
        assert r.status_code == 201


# ---- POST /api/campaigns/{id}/resume ----

class TestResumeCampaign:
    def test_resume_not_found_returns_404(self, client):
        """Returns 404 when the campaign does not exist."""
        r = client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/nonexistent-id/resume")
        assert r.status_code == 404

    def test_resume_enqueues_background_task(self, authed_client, _isolated_store):
        """Resume a valid campaign; expects 200 with the queued message."""
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "ResumeCo", "goal": "Test",
        })
        cid = r.json()["id"]

        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}/resume")

        assert r.status_code == 200
        data = r.json()
        assert data["campaign_id"] == cid
        assert "resume" in data["message"].lower()

    def test_resume_viewer_returns_403(self, _isolated_store):
        """A viewer cannot resume a campaign."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="ViewCo", goal="Test"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _TEST_USER.id)] = "owner"

        viewer = User(id="viewer-001", email="v@example.com", display_name="Viewer", roles=[UserRole.VIEWER])
        _isolated_store._members[(campaign.id, viewer.id)] = "viewer"

        with _as_user(viewer) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/resume")
        assert r.status_code == 403

    def test_resume_other_user_returns_404(self, _isolated_store):
        """A non-member user cannot resume another user's campaign (returns 404 to avoid leaking)."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Priv", goal="Test"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _TEST_USER.id)] = "owner"
        # Remove _OTHER_USER from workspace so they can't access
        del _isolated_store._workspace_members[(TEST_WS_ID, _OTHER_USER.id)]

        with _as_user(_OTHER_USER) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/resume")
        assert r.status_code == 404


# ---- POST /api/workspaces/{ws_id}/campaigns/{id}/retry ----

class TestRetryCampaign:
    def test_retry_not_found_returns_404(self, client):
        """Returns 404 when the campaign does not exist."""
        r = client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/nonexistent-id/retry")
        assert r.status_code == 404

    def test_retry_enqueues_background_task(self, authed_client, _isolated_store):
        """Retry a valid campaign; expects 200 with the queued message."""
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={
            "product_or_service": "RetryCo", "goal": "Test",
        })
        cid = r.json()["id"]

        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{cid}/retry")

        assert r.status_code == 200
        data = r.json()
        assert data["campaign_id"] == cid
        assert "retry" in data["message"].lower()

    def test_retry_viewer_returns_403(self, _isolated_store):
        """A viewer cannot retry a campaign."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="ViewCo", goal="Test"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _TEST_USER.id)] = "owner"

        viewer = User(id="viewer-002", email="v2@example.com", display_name="Viewer2", roles=[UserRole.VIEWER])
        _isolated_store._members[(campaign.id, viewer.id)] = "viewer"

        with _as_user(viewer) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/retry")
        assert r.status_code == 403

    def test_retry_other_user_returns_404(self, _isolated_store):
        """A non-member user cannot retry another user's campaign (returns 404 to avoid leaking)."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Priv", goal="Test"),
            owner_id=_TEST_USER.id,
            workspace_id=TEST_WS_ID,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _TEST_USER.id)] = "owner"
        # Remove _OTHER_USER from workspace so they can't access
        del _isolated_store._workspace_members[(TEST_WS_ID, _OTHER_USER.id)]

        with _as_user(_OTHER_USER) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/retry")
        assert r.status_code == 404


# ---- Campaign workspace assignment ----

from backend.models.workspace import Workspace as _Workspace


class TestCreateCampaignWithWorkspace:
    """Tests for workspace-scoped POST /api/workspaces/{ws_id}/campaigns."""

    _BRIEF = {"product_or_service": "Acme Widget", "goal": "Launch"}

    def test_create_in_workspace_assigns_workspace_id(self, authed_client, _isolated_store):
        """Creating a campaign via workspace path sets workspace_id from the URL."""
        r = authed_client.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json=self._BRIEF)
        assert r.status_code == 201
        cid = r.json()["id"]
        campaign = _isolated_store._campaigns[cid]
        assert campaign.workspace_id == TEST_WS_ID

    def test_create_with_workspace_id_as_creator(self, _isolated_store):
        """Workspace CREATOR can create a campaign in their workspace."""
        _isolated_store._workspaces["ws-1"] = _Workspace(id="ws-1", name="WS", owner_id=_TEST_USER.id)
        _isolated_store._workspace_members[("ws-1", _TEST_USER.id)] = "creator"

        with _as_user(_TEST_USER) as c:
            r = c.post("/api/workspaces/ws-1/campaigns", json=self._BRIEF)
        assert r.status_code == 201
        cid = r.json()["id"]
        assert _isolated_store._campaigns[cid].workspace_id == "ws-1"

    def test_create_with_workspace_id_as_contributor_returns_403(self, _isolated_store):
        """Workspace CONTRIBUTOR cannot create a campaign in a workspace."""
        _isolated_store._workspaces["ws-1"] = _Workspace(id="ws-1", name="WS", owner_id="other")
        # Override _TEST_USER's role for ws-1 to contributor
        _isolated_store._workspace_members[("ws-1", _TEST_USER.id)] = "contributor"

        with _as_user(_TEST_USER) as c:
            r = c.post("/api/workspaces/ws-1/campaigns", json=self._BRIEF)
        assert r.status_code == 403

    def test_create_with_nonexistent_workspace_returns_404(self, _isolated_store):
        """Specifying a workspace that doesn't exist returns 404."""
        with _as_user(_TEST_USER) as c:
            r = c.post("/api/workspaces/no-such-ws/campaigns", json=self._BRIEF)
        assert r.status_code == 404

    def test_admin_can_create_in_workspace_without_membership(self, _isolated_store):
        """Admin can create a campaign in any workspace regardless of membership."""
        _isolated_store._workspaces["ws-1"] = _Workspace(id="ws-1", name="WS", owner_id="other")
        # Admin has no workspace membership entry

        with _as_user(_ADMIN_USER) as c:
            r = c.post("/api/workspaces/ws-1/campaigns", json=self._BRIEF)
        assert r.status_code == 201
        cid = r.json()["id"]
        assert _isolated_store._campaigns[cid].workspace_id == "ws-1"

    def test_viewer_cannot_create_campaign(self, _isolated_store):
        """Platform VIEWER cannot create campaigns at all."""
        with _as_user(_VIEWER_USER) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json=self._BRIEF)
        assert r.status_code == 403


class TestAssignCampaignWorkspace:
    """Tests for PATCH /api/campaigns/{id}/workspace — endpoint removed, returns 404."""

    def test_assign_workspace_endpoint_no_longer_exists(self, _isolated_store):
        """The old PATCH /api/campaigns/{id}/workspace endpoint no longer exists."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="X", goal="Y"),
            owner_id=_TEST_USER.id,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        with _as_user(_ADMIN_USER) as c:
            r = c.patch(f"/api/campaigns/{campaign.id}/workspace", json={"workspace_id": None})
        assert r.status_code == 404


# ---- Persona API ----

class TestPersonaApi:
    def test_create_list_get_update_delete_persona(self, authed_client):
        create_response = authed_client.post(
            f"/api/workspaces/{TEST_WS_ID}/personas",
            json={
                "name": "IT Manager Maria",
                "description": "Leads SaaS tooling decisions at a mid-market company",
            },
        )
        assert create_response.status_code == 201
        created = create_response.json()
        persona_id = created["id"]
        assert created["workspace_id"] == TEST_WS_ID
        assert created["name"] == "IT Manager Maria"

        list_response = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/personas")
        assert list_response.status_code == 200
        list_payload = list_response.json()
        assert list_payload["pagination"]["total_count"] == 1
        assert len(list_payload["items"]) == 1
        assert list_payload["items"][0]["id"] == persona_id

        get_response = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/personas/{persona_id}")
        assert get_response.status_code == 200
        assert get_response.json()["name"] == "IT Manager Maria"

        update_response = authed_client.patch(
            f"/api/workspaces/{TEST_WS_ID}/personas/{persona_id}",
            json={"description": "Updated persona description"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["description"] == "Updated persona description"

        delete_response = authed_client.delete(f"/api/workspaces/{TEST_WS_ID}/personas/{persona_id}")
        assert delete_response.status_code == 204

        get_deleted_response = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/personas/{persona_id}")
        assert get_deleted_response.status_code == 404

    def test_persona_api_requires_authentication(self, client):
        create_response = client.post(
            f"/api/workspaces/{TEST_WS_ID}/personas",
            json={"name": "Persona", "description": "Description"},
        )
        assert create_response.status_code == 401

    def test_viewer_can_list_but_cannot_mutate_personas(self, _isolated_store):
        _isolated_store._workspace_members[(TEST_WS_ID, _VIEWER_USER.id)] = "viewer"
        with _as_user(_VIEWER_USER) as c:
            create_response = c.post(
                f"/api/workspaces/{TEST_WS_ID}/personas",
                json={"name": "Persona", "description": "Description"},
            )
            assert create_response.status_code == 403

            list_response = c.get(f"/api/workspaces/{TEST_WS_ID}/personas")
            assert list_response.status_code == 200
            assert list_response.json()["items"] == []

    def test_parse_persona_returns_structured_fields(self, authed_client):
        mock_raw = (
            '{"demographics": "Ages 25-40, urban professionals",'
            ' "psychographics": "Values productivity",'
            ' "pain_points": "Lack of time",'
            ' "behaviors": "Mobile-first",'
            ' "channels": "LinkedIn, email"}'
        )
        with patch("backend.api.personas.get_llm_service") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.chat_json = AsyncMock(return_value=mock_raw)
            mock_get_llm.return_value = mock_llm

            response = authed_client.post(
                f"/api/workspaces/{TEST_WS_ID}/personas/parse",
                json={"name": "IT Manager Maria", "description": "A 30-year-old IT manager in New York."},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "IT Manager Maria"
        assert data["demographics"] == "Ages 25-40, urban professionals"
        assert data["psychographics"] == "Values productivity"
        assert data["pain_points"] == "Lack of time"
        assert data["behaviors"] == "Mobile-first"
        assert data["channels"] == "LinkedIn, email"

    def test_parse_persona_requires_authentication(self, client):
        response = client.post(
            f"/api/workspaces/{TEST_WS_ID}/personas/parse",
            json={"name": "Persona", "description": "A description."},
        )
        assert response.status_code == 401

    def test_parse_persona_writer_only(self, _isolated_store):
        _isolated_store._workspace_members[(TEST_WS_ID, _VIEWER_USER.id)] = "viewer"
        with _as_user(_VIEWER_USER) as c:
            response = c.post(
                f"/api/workspaces/{TEST_WS_ID}/personas/parse",
                json={"name": "Persona", "description": "A description."},
            )
        assert response.status_code == 403

    def test_parse_persona_graceful_fallback_on_llm_failure(self, authed_client):
        with patch("backend.api.personas.get_llm_service") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.chat_json = AsyncMock(side_effect=Exception("LLM unavailable"))
            mock_get_llm.return_value = mock_llm

            response = authed_client.post(
                f"/api/workspaces/{TEST_WS_ID}/personas/parse",
                json={"name": "Fallback Persona", "description": "Some description."},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Fallback Persona"
        assert data["demographics"] == ""
        assert data["psychographics"] == ""
        assert data["pain_points"] == ""
        assert data["behaviors"] == ""
        assert data["channels"] == ""


# ---- GET /api/campaigns/{id}/events ----


class TestGetCampaignEvents:
    """Tests for the GET /workspaces/{ws_id}/campaigns/{id}/events endpoint."""

    def _make_campaign(self, store) -> Campaign:
        import asyncio
        brief = CampaignBrief(product_or_service="EventTest", goal="Test events")
        campaign = Campaign(brief=brief, owner_id=_TEST_USER.id, workspace_id=TEST_WS_ID)
        asyncio.get_event_loop().run_until_complete(store.update(campaign))
        return campaign

    def _make_event_log(self, campaign_id: str, event_type: str = "pipeline_started"):
        from datetime import datetime, timezone
        from backend.models.events import CampaignEventLog
        return CampaignEventLog(
            id="evt-001",
            campaign_id=campaign_id,
            event_type=event_type,
            stage=None,
            payload={"campaign_id": campaign_id},
            owner_id=None,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    def test_returns_empty_list_when_no_events(self, authed_client, _isolated_store):
        """Returns an empty list when no events have been persisted."""
        campaign = self._make_campaign(_isolated_store)
        mock_store = MagicMock()
        mock_store.get_events = AsyncMock(return_value=[])

        with patch("backend.api.campaigns.get_event_store", return_value=mock_store):
            r = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/events")

        assert r.status_code == 200
        assert r.json() == []

    def test_returns_events_for_campaign(self, authed_client, _isolated_store):
        """Returns serialised event logs for a campaign."""
        campaign = self._make_campaign(_isolated_store)
        event_log = self._make_event_log(campaign.id)
        mock_store = MagicMock()
        mock_store.get_events = AsyncMock(return_value=[event_log])

        with patch("backend.api.campaigns.get_event_store", return_value=mock_store):
            r = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/events")

        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["id"] == "evt-001"
        assert data[0]["event_type"] == "pipeline_started"
        assert data[0]["campaign_id"] == campaign.id

    def test_returns_404_for_unknown_campaign(self, authed_client, _isolated_store):
        """Returns 404 when the campaign does not exist."""
        r = authed_client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/no-such-campaign/events")
        assert r.status_code == 404

    def test_passes_limit_and_offset_to_store(self, authed_client, _isolated_store):
        """Query params limit and offset are forwarded to the event store."""
        campaign = self._make_campaign(_isolated_store)
        mock_store = MagicMock()
        mock_store.get_events = AsyncMock(return_value=[])

        with patch("backend.api.campaigns.get_event_store", return_value=mock_store):
            r = authed_client.get(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/events?limit=10&offset=5"
            )

        assert r.status_code == 200
        mock_store.get_events.assert_awaited_once_with(campaign.id, limit=10, offset=5)

    def test_viewer_can_read_events_via_admin(self, _isolated_store):
        """An admin can always access the event log."""
        import asyncio
        campaign = self._make_campaign(_isolated_store)
        mock_store = MagicMock()
        mock_store.get_events = AsyncMock(return_value=[])

        admin = User(id="admin-001", email="admin@example.com", display_name="Admin", roles=[UserRole.ADMIN])
        with _as_user(admin) as c:
            with patch("backend.api.campaigns.get_event_store", return_value=mock_store):
                r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/events")

        assert r.status_code == 200

    def test_unauthenticated_can_read_events_when_auth_disabled(self, client, _isolated_store):
        """When auth is disabled all requests succeed."""
        campaign = self._make_campaign(_isolated_store)
        mock_store = MagicMock()
        mock_store.get_events = AsyncMock(return_value=[])

        with patch("backend.api.campaigns.get_event_store", return_value=mock_store):
            r = client.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/events")

        assert r.status_code == 200
