"""
Tests for workspace CRUD and workspace membership management.

Covers:
  Workspace CRUD:
  - Create workspace succeeds for campaign_builder
  - Create workspace succeeds for admin
  - Create workspace fails for viewer (403)
  - Get workspace succeeds for member
  - Get workspace returns 404 for non-member
  - Admin can see any workspace
  - Update workspace succeeds for CREATOR
  - Update workspace fails for CONTRIBUTOR (403)
  - Delete workspace orphans campaigns (sets workspace_id=NULL)
  - Delete personal workspace is forbidden
  - List workspaces returns only user's workspaces
  - Admin list workspaces returns all

  Workspace membership:
  - List members succeeds for any workspace member
  - Add member succeeds for CREATOR
  - Add member fails for CONTRIBUTOR (403)
  - Update member role succeeds for CREATOR
  - Remove member succeeds for CREATOR
  - Cannot remove last CREATOR
  - Inactive user cannot be added as member
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.campaign import Campaign, CampaignBrief
from backend.models.user import User, UserRole
from backend.models.workspace import Workspace
from backend.services.auth import get_current_user
from backend.tests.mock_store import InMemoryCampaignStore


# ---------------------------------------------------------------------------
# Module-level users
# ---------------------------------------------------------------------------

_BUILDER = User(
    id="ws-test-builder-001",
    email="builder@ws.test",
    display_name="Builder",
    roles=[UserRole.CAMPAIGN_BUILDER],
)
_BUILDER2 = User(
    id="ws-test-builder-002",
    email="builder2@ws.test",
    display_name="Builder2",
    roles=[UserRole.CAMPAIGN_BUILDER],
)
_ADMIN = User(
    id="ws-test-admin-001",
    email="admin@ws.test",
    display_name="Admin",
    roles=[UserRole.ADMIN],
)
_VIEWER = User(
    id="ws-test-viewer-001",
    email="viewer@ws.test",
    display_name="Viewer",
    roles=[UserRole.VIEWER],
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_store():
    """Fresh in-memory store for every test; patch all store references."""
    store = InMemoryCampaignStore()
    mock_executor = MagicMock()
    mock_executor.dispatch = AsyncMock()
    with (
        patch("backend.api.campaigns.get_campaign_store", return_value=store),
        patch("backend.api.workspaces.get_campaign_store", return_value=store),
        patch("backend.application.campaign_workflow_service.get_campaign_store", return_value=store),
        patch("backend.application.campaign_workflow_service._workflow_service", None),
        patch("backend.api.campaigns.get_executor", return_value=mock_executor),
        patch("backend.api.campaign_workflow.get_executor", return_value=mock_executor),
        patch("backend.apps.api.startup.init_db", new_callable=AsyncMock),
        patch("backend.apps.api.startup.close_db", new_callable=AsyncMock),
    ):
        yield store


@contextmanager
def _as_user(user: User):
    """TestClient context with *user* as the authenticated principal."""
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _make_workspace(
    workspace_id: str,
    name: str,
    owner_id: str,
    is_personal: bool = False,
) -> Workspace:
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


def _make_campaign(store: InMemoryCampaignStore, workspace_id: str) -> Campaign:
    brief = CampaignBrief(product_or_service="Test Product", goal="Test Goal")
    campaign = Campaign(brief=brief, workspace_id=workspace_id)
    store._campaigns[campaign.id] = campaign
    return campaign


# ---------------------------------------------------------------------------
# Workspace CRUD tests
# ---------------------------------------------------------------------------

class TestCreateWorkspace:
    """POST /api/workspaces"""

    def test_create_workspace_succeeds_for_campaign_builder(self):
        with _as_user(_BUILDER) as c:
            r = c.post("/api/workspaces", json={"name": "Builder Workspace"})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Builder Workspace"
        assert data["owner_id"] == _BUILDER.id
        assert data["is_personal"] is False

    def test_create_workspace_succeeds_for_admin(self):
        with _as_user(_ADMIN) as c:
            r = c.post("/api/workspaces", json={"name": "Admin Workspace"})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Admin Workspace"
        assert data["owner_id"] == _ADMIN.id

    def test_create_workspace_fails_for_viewer(self):
        with _as_user(_VIEWER) as c:
            r = c.post("/api/workspaces", json={"name": "Viewer Workspace"})
        assert r.status_code == 403

    def test_create_workspace_with_description(self):
        with _as_user(_BUILDER) as c:
            r = c.post(
                "/api/workspaces",
                json={"name": "Described WS", "description": "A detailed description"},
            )
        assert r.status_code == 201
        assert r.json()["description"] == "A detailed description"


class TestGetWorkspace:
    """GET /api/workspaces/{id}"""

    def test_get_workspace_succeeds_for_member(self, _isolated_store):
        _isolated_store._workspaces["ws-get"] = _make_workspace("ws-get", "Get WS", _BUILDER.id)
        _isolated_store._workspace_members[("ws-get", _BUILDER.id)] = "creator"

        with _as_user(_BUILDER) as c:
            r = c.get("/api/workspaces/ws-get")
        assert r.status_code == 200
        assert r.json()["id"] == "ws-get"
        assert r.json()["name"] == "Get WS"

    def test_get_workspace_returns_404_for_non_member(self, _isolated_store):
        _isolated_store._workspaces["ws-get"] = _make_workspace("ws-get", "Get WS", "other-owner")

        with _as_user(_BUILDER) as c:
            r = c.get("/api/workspaces/ws-get")
        assert r.status_code == 404

    def test_admin_can_see_any_workspace(self, _isolated_store):
        _isolated_store._workspaces["ws-any"] = _make_workspace("ws-any", "Any WS", "some-owner")

        with _as_user(_ADMIN) as c:
            r = c.get("/api/workspaces/ws-any")
        assert r.status_code == 200

    def test_get_unknown_workspace_returns_404(self):
        with _as_user(_BUILDER) as c:
            r = c.get("/api/workspaces/does-not-exist")
        assert r.status_code == 404


class TestListWorkspaces:
    """GET /api/workspaces"""

    def test_list_workspaces_returns_only_users_workspaces(self, _isolated_store):
        _isolated_store._workspaces["ws-mine"] = _make_workspace("ws-mine", "Mine", _BUILDER.id)
        _isolated_store._workspace_members[("ws-mine", _BUILDER.id)] = "creator"
        _isolated_store._workspaces["ws-other"] = _make_workspace("ws-other", "Other", _BUILDER2.id)
        _isolated_store._workspace_members[("ws-other", _BUILDER2.id)] = "creator"

        with _as_user(_BUILDER) as c:
            r = c.get("/api/workspaces")
        assert r.status_code == 200
        ids = [w["id"] for w in r.json()]
        assert "ws-mine" in ids
        assert "ws-other" not in ids

    def test_admin_list_workspaces_returns_all(self, _isolated_store):
        _isolated_store._workspaces["ws-a"] = _make_workspace("ws-a", "WS A", _BUILDER.id)
        _isolated_store._workspaces["ws-b"] = _make_workspace("ws-b", "WS B", _BUILDER2.id)

        with _as_user(_ADMIN) as c:
            r = c.get("/api/workspaces")
        assert r.status_code == 200
        ids = [w["id"] for w in r.json()]
        assert "ws-a" in ids
        assert "ws-b" in ids

    def test_contributor_sees_workspaces_they_are_member_of(self, _isolated_store):
        _isolated_store._workspaces["ws-contrib"] = _make_workspace("ws-contrib", "Contrib WS", _BUILDER.id)
        _isolated_store._workspace_members[("ws-contrib", _BUILDER2.id)] = "contributor"

        with _as_user(_BUILDER2) as c:
            r = c.get("/api/workspaces")
        assert r.status_code == 200
        ids = [w["id"] for w in r.json()]
        assert "ws-contrib" in ids


class TestUpdateWorkspace:
    """PATCH /api/workspaces/{id}"""

    def test_update_workspace_succeeds_for_creator(self, _isolated_store):
        _isolated_store._workspaces["ws-upd"] = _make_workspace("ws-upd", "Old Name", _BUILDER.id)
        _isolated_store._workspace_members[("ws-upd", _BUILDER.id)] = "creator"

        with _as_user(_BUILDER) as c:
            r = c.patch("/api/workspaces/ws-upd", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    def test_update_workspace_fails_for_contributor(self, _isolated_store):
        _isolated_store._workspaces["ws-upd"] = _make_workspace("ws-upd", "WS", "owner")
        _isolated_store._workspace_members[("ws-upd", _BUILDER.id)] = "contributor"

        with _as_user(_BUILDER) as c:
            r = c.patch("/api/workspaces/ws-upd", json={"name": "Hacked"})
        assert r.status_code == 403

    def test_update_workspace_fails_for_viewer_member(self, _isolated_store):
        _isolated_store._workspaces["ws-upd"] = _make_workspace("ws-upd", "WS", "owner")
        _isolated_store._workspace_members[("ws-upd", _VIEWER.id)] = "viewer"

        with _as_user(_VIEWER) as c:
            r = c.patch("/api/workspaces/ws-upd", json={"name": "Hacked"})
        assert r.status_code == 403

    def test_update_unknown_workspace_returns_404(self):
        with _as_user(_BUILDER) as c:
            r = c.patch("/api/workspaces/does-not-exist", json={"name": "X"})
        assert r.status_code == 404


class TestDeleteWorkspace:
    """DELETE /api/workspaces/{id}"""

    def test_delete_workspace_orphans_campaigns(self, _isolated_store):
        _isolated_store._workspaces["ws-del"] = _make_workspace("ws-del", "WS", _BUILDER.id)
        _isolated_store._workspace_members[("ws-del", _BUILDER.id)] = "creator"
        campaign = _make_campaign(_isolated_store, "ws-del")

        with _as_user(_BUILDER) as c:
            r = c.delete("/api/workspaces/ws-del")
        assert r.status_code == 204
        assert "ws-del" not in _isolated_store._workspaces
        assert _isolated_store._campaigns[campaign.id].workspace_id is None

    def test_delete_personal_workspace_is_forbidden(self, _isolated_store):
        _isolated_store._workspaces["ws-personal"] = _make_workspace(
            "ws-personal", "Personal", _BUILDER.id, is_personal=True
        )
        _isolated_store._workspace_members[("ws-personal", _BUILDER.id)] = "creator"

        with _as_user(_BUILDER) as c:
            r = c.delete("/api/workspaces/ws-personal")
        assert r.status_code == 409
        assert "ws-personal" in _isolated_store._workspaces

    def test_delete_unknown_workspace_returns_404(self):
        with _as_user(_BUILDER) as c:
            r = c.delete("/api/workspaces/does-not-exist")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Workspace membership tests
# ---------------------------------------------------------------------------

class TestListWorkspaceMembers:
    """GET /api/workspaces/{id}/members"""

    def test_list_members_succeeds_for_any_workspace_member(self, _isolated_store):
        _isolated_store._workspaces["ws-mem"] = _make_workspace("ws-mem", "WS", _BUILDER.id)
        _isolated_store._workspace_members[("ws-mem", _BUILDER.id)] = "creator"
        _isolated_store._workspace_members[("ws-mem", _BUILDER2.id)] = "viewer"

        with _as_user(_BUILDER2) as c:
            r = c.get("/api/workspaces/ws-mem/members")
        assert r.status_code == 200
        user_ids = [m["user_id"] for m in r.json()]
        assert _BUILDER.id in user_ids
        assert _BUILDER2.id in user_ids

    def test_non_member_gets_404_when_listing_members(self, _isolated_store):
        _isolated_store._workspaces["ws-mem"] = _make_workspace("ws-mem", "WS", "owner")

        with _as_user(_BUILDER) as c:
            r = c.get("/api/workspaces/ws-mem/members")
        assert r.status_code == 404


class TestAddWorkspaceMember:
    """POST /api/workspaces/{id}/members"""

    def test_add_member_succeeds_for_creator(self, _isolated_store):
        _isolated_store._workspaces["ws-add"] = _make_workspace("ws-add", "WS", _BUILDER.id)
        _isolated_store._workspace_members[("ws-add", _BUILDER.id)] = "creator"
        _isolated_store._users[_BUILDER2.id] = _BUILDER2

        with _as_user(_BUILDER) as c:
            r = c.post(
                "/api/workspaces/ws-add/members",
                json={"user_id": _BUILDER2.id, "role": "contributor"},
            )
        assert r.status_code == 201
        assert r.json()["user_id"] == _BUILDER2.id
        assert r.json()["role"] == "contributor"
        assert ("ws-add", _BUILDER2.id) in _isolated_store._workspace_members

    def test_add_member_fails_for_contributor(self, _isolated_store):
        _isolated_store._workspaces["ws-add"] = _make_workspace("ws-add", "WS", "owner")
        _isolated_store._workspace_members[("ws-add", _BUILDER.id)] = "contributor"
        _isolated_store._users[_BUILDER2.id] = _BUILDER2

        with _as_user(_BUILDER) as c:
            r = c.post(
                "/api/workspaces/ws-add/members",
                json={"user_id": _BUILDER2.id, "role": "viewer"},
            )
        assert r.status_code == 403

    def test_inactive_user_cannot_be_added_as_member(self, _isolated_store):
        _isolated_store._workspaces["ws-add"] = _make_workspace("ws-add", "WS", _BUILDER.id)
        _isolated_store._workspace_members[("ws-add", _BUILDER.id)] = "creator"
        inactive = User(
            id="inactive-ws-001",
            email="inactive@ws.test",
            display_name="Inactive",
            roles=[UserRole.CAMPAIGN_BUILDER],
            is_active=False,
        )
        _isolated_store._users[inactive.id] = inactive

        with _as_user(_BUILDER) as c:
            r = c.post(
                "/api/workspaces/ws-add/members",
                json={"user_id": inactive.id, "role": "viewer"},
            )
        assert r.status_code == 404

    def test_add_unknown_user_returns_404(self, _isolated_store):
        _isolated_store._workspaces["ws-add"] = _make_workspace("ws-add", "WS", _BUILDER.id)
        _isolated_store._workspace_members[("ws-add", _BUILDER.id)] = "creator"

        with _as_user(_BUILDER) as c:
            r = c.post(
                "/api/workspaces/ws-add/members",
                json={"user_id": "no-such-user", "role": "viewer"},
            )
        assert r.status_code == 404


class TestUpdateWorkspaceMemberRole:
    """PATCH /api/workspaces/{id}/members/{user_id}"""

    def test_update_member_role_succeeds_for_creator(self, _isolated_store):
        _isolated_store._workspaces["ws-upd"] = _make_workspace("ws-upd", "WS", _BUILDER.id)
        _isolated_store._workspace_members[("ws-upd", _BUILDER.id)] = "creator"
        _isolated_store._workspace_members[("ws-upd", _BUILDER2.id)] = "viewer"

        with _as_user(_BUILDER) as c:
            r = c.patch(
                f"/api/workspaces/ws-upd/members/{_BUILDER2.id}",
                json={"role": "contributor"},
            )
        assert r.status_code == 200
        assert r.json()["role"] == "contributor"
        assert _isolated_store._workspace_members[("ws-upd", _BUILDER2.id)] == "contributor"

    def test_update_role_for_non_member_returns_404(self, _isolated_store):
        _isolated_store._workspaces["ws-upd"] = _make_workspace("ws-upd", "WS", _BUILDER.id)
        _isolated_store._workspace_members[("ws-upd", _BUILDER.id)] = "creator"

        with _as_user(_BUILDER) as c:
            r = c.patch(
                "/api/workspaces/ws-upd/members/no-such-user",
                json={"role": "contributor"},
            )
        assert r.status_code == 404

    def test_contributor_cannot_update_member_role(self, _isolated_store):
        _isolated_store._workspaces["ws-upd"] = _make_workspace("ws-upd", "WS", "owner")
        _isolated_store._workspace_members[("ws-upd", _BUILDER.id)] = "contributor"
        _isolated_store._workspace_members[("ws-upd", _BUILDER2.id)] = "viewer"

        with _as_user(_BUILDER) as c:
            r = c.patch(
                f"/api/workspaces/ws-upd/members/{_BUILDER2.id}",
                json={"role": "contributor"},
            )
        assert r.status_code == 403


class TestRemoveWorkspaceMember:
    """DELETE /api/workspaces/{id}/members/{user_id}"""

    def test_remove_member_succeeds_for_creator(self, _isolated_store):
        _isolated_store._workspaces["ws-rem"] = _make_workspace("ws-rem", "WS", _BUILDER.id)
        _isolated_store._workspace_members[("ws-rem", _BUILDER.id)] = "creator"
        _isolated_store._workspace_members[("ws-rem", _BUILDER2.id)] = "viewer"

        with _as_user(_BUILDER) as c:
            r = c.delete(f"/api/workspaces/ws-rem/members/{_BUILDER2.id}")
        assert r.status_code == 204
        assert ("ws-rem", _BUILDER2.id) not in _isolated_store._workspace_members

    def test_cannot_remove_last_creator(self, _isolated_store):
        _isolated_store._workspaces["ws-rem"] = _make_workspace("ws-rem", "WS", _BUILDER.id)
        _isolated_store._workspace_members[("ws-rem", _BUILDER.id)] = "creator"

        with _as_user(_BUILDER) as c:
            r = c.delete(f"/api/workspaces/ws-rem/members/{_BUILDER.id}")
        assert r.status_code == 409
        assert ("ws-rem", _BUILDER.id) in _isolated_store._workspace_members

    def test_remove_non_existent_member_returns_404(self, _isolated_store):
        _isolated_store._workspaces["ws-rem"] = _make_workspace("ws-rem", "WS", _BUILDER.id)
        _isolated_store._workspace_members[("ws-rem", _BUILDER.id)] = "creator"

        with _as_user(_BUILDER) as c:
            r = c.delete("/api/workspaces/ws-rem/members/no-such-user")
        assert r.status_code == 404
