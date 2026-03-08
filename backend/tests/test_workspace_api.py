"""
Tests for the workspace REST API routes.

Uses FastAPI's TestClient (synchronous) to test all endpoints.
The in-memory async store replaces the PostgreSQL-backed store so no
database is required.
"""

from __future__ import annotations

import pytest
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient

from backend.main import app
from backend.models.user import User, UserRole
from backend.services.auth import get_current_user
from backend.tests.mock_store import InMemoryCampaignStore

_CREATOR_USER = User(
    id="creator-001",
    email="creator@example.com",
    display_name="Creator User",
    roles=[UserRole.CAMPAIGN_BUILDER],
)
_OTHER_USER = User(
    id="other-002",
    email="other@example.com",
    display_name="Other User",
    roles=[UserRole.CAMPAIGN_BUILDER],
)
_ADMIN_USER = User(
    id="admin-003",
    email="admin@example.com",
    display_name="Admin User",
    roles=[UserRole.ADMIN],
)
_VIEWER_USER = User(
    id="viewer-004",
    email="viewer@example.com",
    display_name="Viewer User",
    roles=[UserRole.VIEWER],
)


@pytest.fixture(autouse=True)
def _isolated_store():
    """Give each test a fresh InMemoryCampaignStore and mock the pipeline."""
    fresh_store = InMemoryCampaignStore()
    mock_executor = MagicMock()
    mock_executor.dispatch = AsyncMock()

    with (
        patch("backend.api.campaigns.get_campaign_store", return_value=fresh_store),
        patch("backend.api.workspaces.get_campaign_store", return_value=fresh_store),
        patch("backend.application.campaign_workflow_service.get_campaign_store", return_value=fresh_store),
        patch("backend.application.campaign_workflow_service._workflow_service", None),
        patch("backend.api.campaigns.get_executor", return_value=mock_executor),
        patch("backend.api.campaign_workflow.get_executor", return_value=mock_executor),
        patch("backend.apps.api.startup.init_db", new_callable=AsyncMock),
        patch("backend.apps.api.startup.close_db", new_callable=AsyncMock),
    ):
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
def creator_client():
    """Client authenticated as the CREATOR_USER."""
    app.dependency_overrides[get_current_user] = lambda: _CREATOR_USER
    c = TestClient(app, raise_server_exceptions=False)
    yield c
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def admin_client():
    """Client authenticated as ADMIN_USER."""
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
    c = TestClient(app, raise_server_exceptions=False)
    yield c
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# POST /api/workspaces
# ---------------------------------------------------------------------------

class TestCreateWorkspace:
    def test_create_workspace_returns_201(self, creator_client):
        r = creator_client.post("/api/workspaces", json={"name": "My Workspace"})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "My Workspace"
        assert data["description"] is None
        assert data["owner_id"] == _CREATOR_USER.id
        assert data["is_personal"] is False
        assert "id" in data

    def test_create_workspace_with_description(self, creator_client):
        r = creator_client.post(
            "/api/workspaces",
            json={"name": "Team WS", "description": "For the team"},
        )
        assert r.status_code == 201
        assert r.json()["description"] == "For the team"

    def test_viewer_cannot_create_workspace(self):
        with _as_user(_VIEWER_USER) as c:
            r = c.post("/api/workspaces", json={"name": "Nope"})
        assert r.status_code == 403

    def test_auth_disabled_creates_workspace(self, client):
        r = client.post("/api/workspaces", json={"name": "Dev Workspace"})
        assert r.status_code == 201
        assert r.json()["owner_id"] == "local"


# ---------------------------------------------------------------------------
# GET /api/workspaces
# ---------------------------------------------------------------------------

class TestListWorkspaces:
    def test_list_returns_only_own_workspaces(self, _isolated_store, creator_client):
        _isolated_store._workspaces["ws-a"] = _make_workspace("ws-a", "WS A", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-a", _CREATOR_USER.id)] = "creator"
        _isolated_store._workspaces["ws-b"] = _make_workspace("ws-b", "WS B", "other-owner")

        r = creator_client.get("/api/workspaces")
        assert r.status_code == 200
        ids = [w["id"] for w in r.json()]
        assert "ws-a" in ids
        assert "ws-b" not in ids

    def test_admin_sees_all_workspaces(self, _isolated_store, admin_client):
        _isolated_store._workspaces["ws-a"] = _make_workspace("ws-a", "WS A", _CREATOR_USER.id)
        _isolated_store._workspaces["ws-b"] = _make_workspace("ws-b", "WS B", "other-owner")

        r = admin_client.get("/api/workspaces")
        assert r.status_code == 200
        ids = [w["id"] for w in r.json()]
        assert "ws-a" in ids
        assert "ws-b" in ids

    def test_workspace_summary_includes_role(self, _isolated_store, creator_client):
        _isolated_store._workspaces["ws-a"] = _make_workspace("ws-a", "WS A", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-a", _CREATOR_USER.id)] = "creator"

        r = creator_client.get("/api/workspaces")
        assert r.status_code == 200
        ws = next(w for w in r.json() if w["id"] == "ws-a")
        assert ws["role"] == "creator"


# ---------------------------------------------------------------------------
# GET /api/workspaces/{id}
# ---------------------------------------------------------------------------

class TestGetWorkspace:
    def test_get_returns_workspace_details(self, _isolated_store, creator_client):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "Alpha", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "creator"

        r = creator_client.get("/api/workspaces/ws-1")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "ws-1"
        assert data["name"] == "Alpha"

    def test_non_member_gets_404(self, _isolated_store):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "Alpha", "other")
        with _as_user(_CREATOR_USER) as c:
            r = c.get("/api/workspaces/ws-1")
        assert r.status_code == 404

    def test_unknown_workspace_returns_404(self, creator_client):
        r = creator_client.get("/api/workspaces/no-such-ws")
        assert r.status_code == 404

    def test_admin_can_access_any_workspace(self, _isolated_store, admin_client):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "Alpha", "other")
        r = admin_client.get("/api/workspaces/ws-1")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# PATCH /api/workspaces/{id}
# ---------------------------------------------------------------------------

class TestUpdateWorkspace:
    def test_creator_can_update_name(self, _isolated_store, creator_client):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "Old", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "creator"

        r = creator_client.patch("/api/workspaces/ws-1", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    def test_contributor_cannot_update(self, _isolated_store):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", "owner")
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "contributor"
        with _as_user(_CREATOR_USER) as c:
            r = c.patch("/api/workspaces/ws-1", json={"name": "Hacked"})
        assert r.status_code == 403

    def test_viewer_cannot_update(self, _isolated_store):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", "owner")
        _isolated_store._workspace_members[("ws-1", _VIEWER_USER.id)] = "viewer"
        with _as_user(_VIEWER_USER) as c:
            r = c.patch("/api/workspaces/ws-1", json={"name": "Hacked"})
        assert r.status_code == 403

    def test_unknown_workspace_returns_404(self, creator_client):
        r = creator_client.patch("/api/workspaces/no-such-ws", json={"name": "X"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/workspaces/{id}
# ---------------------------------------------------------------------------

class TestDeleteWorkspace:
    def test_creator_can_delete_workspace(self, _isolated_store, creator_client):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "creator"

        r = creator_client.delete("/api/workspaces/ws-1")
        assert r.status_code == 204
        assert "ws-1" not in _isolated_store._workspaces

    def test_personal_workspace_cannot_be_deleted(self, _isolated_store, creator_client):
        _isolated_store._workspaces["ws-personal"] = _make_workspace(
            "ws-personal", "Personal", _CREATOR_USER.id, is_personal=True
        )
        _isolated_store._workspace_members[("ws-personal", _CREATOR_USER.id)] = "creator"

        r = creator_client.delete("/api/workspaces/ws-personal")
        assert r.status_code == 409
        assert "ws-personal" in _isolated_store._workspaces

    def test_contributor_cannot_delete(self, _isolated_store):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", "owner")
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "contributor"
        with _as_user(_CREATOR_USER) as c:
            r = c.delete("/api/workspaces/ws-1")
        assert r.status_code == 403

    def test_unknown_workspace_returns_404(self, creator_client):
        r = creator_client.delete("/api/workspaces/no-such-ws")
        assert r.status_code == 404

    def test_delete_orphans_campaigns(self, _isolated_store, creator_client):
        from backend.models.campaign import Campaign, CampaignBrief
        brief = CampaignBrief(
            product_or_service="X", goal="Y", budget=100, currency="USD",
            start_date="2026-01-01", end_date="2026-12-31",
        )
        campaign = Campaign(brief=brief, workspace_id="ws-1")
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "creator"

        r = creator_client.delete("/api/workspaces/ws-1")
        assert r.status_code == 204
        assert _isolated_store._campaigns[campaign.id].workspace_id is None


# ---------------------------------------------------------------------------
# GET /api/workspaces/{id}/campaigns
# ---------------------------------------------------------------------------

class TestListWorkspaceCampaigns:
    def test_member_can_list_campaigns(self, _isolated_store, creator_client):
        from backend.models.campaign import Campaign, CampaignBrief
        brief = CampaignBrief(
            product_or_service="Prod", goal="Goal", budget=100, currency="USD",
            start_date="2026-01-01", end_date="2026-12-31",
        )
        campaign = Campaign(brief=brief, workspace_id="ws-1")
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "creator"

        r = creator_client.get("/api/workspaces/ws-1/campaigns")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["id"] == campaign.id
        assert items[0]["product_or_service"] == "Prod"
        assert items[0]["goal"] == "Goal"
        assert items[0]["workspace_id"] == "ws-1"
        assert items[0]["workspace_name"] == "WS"
        assert "brief" not in items[0]

    def test_non_member_gets_404(self, _isolated_store):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", "owner")
        with _as_user(_CREATOR_USER) as c:
            r = c.get("/api/workspaces/ws-1/campaigns")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/workspaces/{id}/members
# ---------------------------------------------------------------------------

class TestListWorkspaceMembers:
    def test_member_can_list_members(self, _isolated_store, creator_client):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "creator"

        r = creator_client.get("/api/workspaces/ws-1/members")
        assert r.status_code == 200
        members = r.json()
        assert any(m["user_id"] == _CREATOR_USER.id for m in members)

    def test_non_member_gets_404(self, _isolated_store):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", "owner")
        with _as_user(_CREATOR_USER) as c:
            r = c.get("/api/workspaces/ws-1/members")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/workspaces/{id}/members
# ---------------------------------------------------------------------------

class TestAddWorkspaceMember:
    def test_creator_can_add_member(self, _isolated_store, creator_client):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "creator"
        _isolated_store._users[_OTHER_USER.id] = _OTHER_USER

        r = creator_client.post(
            "/api/workspaces/ws-1/members",
            json={"user_id": _OTHER_USER.id, "role": "contributor"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["user_id"] == _OTHER_USER.id
        assert data["role"] == "contributor"
        assert ("ws-1", _OTHER_USER.id) in _isolated_store._workspace_members

    def test_contributor_cannot_add_member(self, _isolated_store):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", "owner")
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "contributor"
        _isolated_store._users[_OTHER_USER.id] = _OTHER_USER

        with _as_user(_CREATOR_USER) as c:
            r = c.post(
                "/api/workspaces/ws-1/members",
                json={"user_id": _OTHER_USER.id, "role": "viewer"},
            )
        assert r.status_code == 403

    def test_add_unknown_user_returns_404(self, _isolated_store, creator_client):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "creator"

        r = creator_client.post(
            "/api/workspaces/ws-1/members",
            json={"user_id": "no-such-user", "role": "viewer"},
        )
        assert r.status_code == 404

    def test_default_role_is_viewer(self, _isolated_store, creator_client):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "creator"
        _isolated_store._users[_OTHER_USER.id] = _OTHER_USER

        r = creator_client.post(
            "/api/workspaces/ws-1/members",
            json={"user_id": _OTHER_USER.id},
        )
        assert r.status_code == 201
        assert r.json()["role"] == "viewer"


# ---------------------------------------------------------------------------
# PATCH /api/workspaces/{id}/members/{user_id}
# ---------------------------------------------------------------------------

class TestUpdateWorkspaceMemberRole:
    def test_creator_can_update_member_role(self, _isolated_store, creator_client):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "creator"
        _isolated_store._workspace_members[("ws-1", _OTHER_USER.id)] = "viewer"

        r = creator_client.patch(
            f"/api/workspaces/ws-1/members/{_OTHER_USER.id}",
            json={"role": "contributor"},
        )
        assert r.status_code == 200
        assert r.json()["role"] == "contributor"
        assert _isolated_store._workspace_members[("ws-1", _OTHER_USER.id)] == "contributor"

    def test_non_member_of_target_returns_404(self, _isolated_store, creator_client):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "creator"

        r = creator_client.patch(
            "/api/workspaces/ws-1/members/no-such-user",
            json={"role": "contributor"},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/workspaces/{id}/members/{user_id}
# ---------------------------------------------------------------------------

class TestRemoveWorkspaceMember:
    def test_creator_can_remove_member(self, _isolated_store, creator_client):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "creator"
        _isolated_store._workspace_members[("ws-1", _OTHER_USER.id)] = "viewer"

        r = creator_client.delete(f"/api/workspaces/ws-1/members/{_OTHER_USER.id}")
        assert r.status_code == 204
        assert ("ws-1", _OTHER_USER.id) not in _isolated_store._workspace_members

    def test_cannot_remove_last_creator(self, _isolated_store, creator_client):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "creator"

        r = creator_client.delete(f"/api/workspaces/ws-1/members/{_CREATOR_USER.id}")
        assert r.status_code == 409

    def test_remove_nonexistent_member_returns_404(self, _isolated_store, creator_client):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "creator"

        r = creator_client.delete("/api/workspaces/ws-1/members/no-such-user")
        assert r.status_code == 404

    def test_contributor_cannot_remove_member(self, _isolated_store):
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", "owner")
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "contributor"
        _isolated_store._workspace_members[("ws-1", _OTHER_USER.id)] = "viewer"

        with _as_user(_CREATOR_USER) as c:
            r = c.delete(f"/api/workspaces/ws-1/members/{_OTHER_USER.id}")
        assert r.status_code == 403

    def test_can_remove_second_creator(self, _isolated_store, creator_client):
        """When there are two CREATORs, removing one should succeed."""
        _isolated_store._workspaces["ws-1"] = _make_workspace("ws-1", "WS", _CREATOR_USER.id)
        _isolated_store._workspace_members[("ws-1", _CREATOR_USER.id)] = "creator"
        _isolated_store._workspace_members[("ws-1", _OTHER_USER.id)] = "creator"

        r = creator_client.delete(f"/api/workspaces/ws-1/members/{_OTHER_USER.id}")
        assert r.status_code == 204


# ---------------------------------------------------------------------------
# Helper factory
# ---------------------------------------------------------------------------

def _make_workspace(
    workspace_id: str,
    name: str,
    owner_id: str,
    is_personal: bool = False,
):
    from backend.models.workspace import Workspace
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return Workspace(
        id=workspace_id,
        name=name,
        description=None,
        owner_id=owner_id,
        is_personal=is_personal,
        created_at=now,
        updated_at=now,
    )
