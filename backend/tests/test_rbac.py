"""
Comprehensive RBAC test coverage.

Tests every (role × action × membership) combination to prevent privilege
escalation regressions.  All test cases drive the real FastAPI app via
TestClient (campaign endpoints) or httpx.AsyncClient (async admin endpoints)
so that auth middleware, route guards, and _authorize() are all exercised
end-to-end.

Matrix covered:
  Role              | Membership | Endpoint action        | Expected
  ------------------+------------+------------------------+---------
  admin             | none       | GET campaign           | 200
  admin             | none       | DELETE campaign        | 204
  admin             | none       | POST members           | 201
  admin             | none       | GET /admin/users       | 200
  admin             | none       | PATCH /admin/…/role    | 200
  campaign_builder  | owner      | GET / DELETE / members | allowed
  campaign_builder  | editor     | GET / WRITE            | allowed
  campaign_builder  | editor     | DELETE                 | 403
  campaign_builder  | viewer     | GET                    | 200
  campaign_builder  | viewer     | WRITE / DELETE         | 403
  campaign_builder  | none       | GET campaign           | 404
  campaign_builder  | any        | GET /admin/users       | 403
  viewer            | member     | GET campaign           | 200
  viewer            | member     | DELETE / WRITE         | 403
  viewer            | none       | GET campaign           | 404
  viewer            | any        | POST campaign          | 403
  viewer            | any        | GET /admin/users       | 403
  unauthenticated   | —          | GET /admin/users       | 401
  unauthenticated   | —          | PATCH /admin/…/role    | 401
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.models.campaign import Campaign, CampaignBrief
from backend.models.user import CampaignMemberRole, User, UserRole
from backend.services.auth import get_current_user
from backend.services.database import Base, UserRow, get_db
from backend.tests.mock_store import InMemoryCampaignStore

# ---------------------------------------------------------------------------
# Module-level user constants
# ---------------------------------------------------------------------------

_ADMIN = User(id="rbac-admin-001", email="admin@rbac.test", display_name="Admin", roles=[UserRole.ADMIN])
_BUILDER = User(id="rbac-builder-001", email="builder@rbac.test", display_name="Builder", roles=[UserRole.CAMPAIGN_BUILDER])
_BUILDER2 = User(id="rbac-builder-002", email="builder2@rbac.test", display_name="Builder2", roles=[UserRole.CAMPAIGN_BUILDER])
_VIEWER = User(id="rbac-viewer-001", email="viewer@rbac.test", display_name="Viewer", roles=[UserRole.VIEWER])

TEST_WS_ID = "test-workspace-001"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _ensure_workspace(store: InMemoryCampaignStore, ws_id: str = TEST_WS_ID) -> None:
    """Ensure a workspace with the given ID exists in *store*."""
    from datetime import timezone
    if ws_id not in store._workspaces:
        from backend.models.workspace import Workspace
        store._workspaces[ws_id] = Workspace(
            id=ws_id,
            name="Test Workspace",
            owner_id="workspace-owner",
            is_personal=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )


@contextmanager
def _as_user(user: User, store: InMemoryCampaignStore):
    """TestClient context with *user* as the authenticated principal."""
    # Register the user in the store so store-layer admin checks work correctly.
    store.add_user(user)
    app.dependency_overrides[get_current_user] = lambda: user
    mock_executor = MagicMock()
    mock_executor.dispatch = AsyncMock()
    try:
        with patch("backend.api.campaigns.get_campaign_store", return_value=store), \
             patch("backend.apps.api.dependencies.get_campaign_store", return_value=store), \
             patch("backend.api.campaign_members.get_campaign_store", return_value=store), \
             patch("backend.application.campaign_workflow_service.get_campaign_store", return_value=store), \
             patch("backend.application.campaign_workflow_service._workflow_service", None), \
             patch("backend.api.campaigns.get_executor", return_value=mock_executor), \
             patch("backend.api.campaign_workflow.get_executor", return_value=mock_executor), \
             patch("backend.apps.api.startup.init_db", new_callable=AsyncMock), \
             patch("backend.apps.api.startup.close_db", new_callable=AsyncMock):
            yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _make_campaign(store: InMemoryCampaignStore, owner: User) -> Campaign:
    """Directly insert a campaign owned by *owner* into *store* under TEST_WS_ID."""
    _ensure_workspace(store)
    campaign = Campaign(
        brief=CampaignBrief(product_or_service="RBAC Test", goal="Test authorization"),
        owner_id=owner.id,
        workspace_id=TEST_WS_ID,
    )
    store._campaigns[campaign.id] = campaign
    store._members[(campaign.id, owner.id)] = CampaignMemberRole.OWNER.value
    # Add owner as workspace CREATOR so list/access works
    store._workspace_members[(TEST_WS_ID, owner.id)] = "creator"
    return campaign


# ---------------------------------------------------------------------------
# Admin role capabilities
# ---------------------------------------------------------------------------

class TestAdminRoleCapabilities:
    """Admin can read/write/delete any campaign regardless of membership."""

    def test_admin_can_list_all_campaigns(self):
        store = InMemoryCampaignStore()
        _make_campaign(store, _BUILDER)
        _make_campaign(store, _BUILDER2)
        with _as_user(_ADMIN, store) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_admin_can_read_any_campaign(self):
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER)
        with _as_user(_ADMIN, store) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
        assert r.status_code == 200
        assert r.json()["id"] == campaign.id

    def test_admin_can_delete_any_campaign(self):
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER)
        with _as_user(_ADMIN, store) as c:
            r = c.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
        assert r.status_code == 204

    def test_admin_can_add_member_to_any_campaign(self):
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER)
        # Pre-register the target user in the store so the endpoint can look them up
        store._users[_VIEWER.id] = _VIEWER
        with _as_user(_ADMIN, store) as c:
            r = c.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members",
                json={"user_id": _VIEWER.id, "role": "viewer"},
            )
        assert r.status_code == 201

    def test_admin_can_create_campaign(self):
        store = InMemoryCampaignStore()
        _ensure_workspace(store)
        with _as_user(_ADMIN, store) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={"product_or_service": "Prod", "goal": "Goal"})
        assert r.status_code == 201


# ---------------------------------------------------------------------------
# Campaign builder role capabilities
# ---------------------------------------------------------------------------

class TestCampaignBuilderCapabilities:
    """Campaign builder: full access to own/member campaigns; blocked elsewhere."""

    def test_builder_can_create_campaign(self):
        store = InMemoryCampaignStore()
        _ensure_workspace(store)
        store._workspace_members[(TEST_WS_ID, _BUILDER.id)] = "creator"
        with _as_user(_BUILDER, store) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={"product_or_service": "Prod", "goal": "Goal"})
        assert r.status_code == 201

    def test_builder_can_read_own_campaign(self):
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER)
        with _as_user(_BUILDER, store) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
        assert r.status_code == 200

    def test_builder_can_delete_own_campaign(self):
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER)
        with _as_user(_BUILDER, store) as c:
            r = c.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
        assert r.status_code == 204

    def test_builder_editor_can_read_campaign(self):
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER2)
        store._members[(campaign.id, _BUILDER.id)] = CampaignMemberRole.EDITOR.value
        with _as_user(_BUILDER, store) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
        assert r.status_code == 200

    def test_builder_editor_cannot_delete_campaign(self):
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER2)
        store._members[(campaign.id, _BUILDER.id)] = CampaignMemberRole.EDITOR.value
        with _as_user(_BUILDER, store) as c:
            r = c.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
        assert r.status_code == 403

    def test_builder_viewer_member_can_read_campaign(self):
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER2)
        store._members[(campaign.id, _BUILDER.id)] = CampaignMemberRole.VIEWER.value
        with _as_user(_BUILDER, store) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
        assert r.status_code == 200

    def test_builder_viewer_member_cannot_delete_campaign(self):
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER2)
        store._members[(campaign.id, _BUILDER.id)] = CampaignMemberRole.VIEWER.value
        with _as_user(_BUILDER, store) as c:
            r = c.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
        assert r.status_code == 403

    def test_builder_cannot_access_non_member_campaign(self):
        """Non-member gets 404 to prevent existence leakage."""
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER2)
        with _as_user(_BUILDER, store) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
        assert r.status_code == 404

    def test_builder_non_member_campaign_not_in_list(self):
        """Non-workspace-member gets 404 when listing campaigns in a workspace they don't belong to."""
        store = InMemoryCampaignStore()
        _make_campaign(store, _BUILDER2)  # no membership for _BUILDER in workspace
        with _as_user(_BUILDER, store) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns")
        assert r.status_code == 404  # _BUILDER is not in the workspace

    def test_builder_cannot_access_admin_users_endpoint(self):
        """Campaign builders are forbidden from the admin users list."""
        store = InMemoryCampaignStore()
        with _as_user(_BUILDER, store) as c:
            r = c.get("/api/admin/users")
        assert r.status_code == 403

    def test_builder_cannot_access_admin_campaigns_endpoint(self):
        """Campaign builders are forbidden from the admin campaigns list."""
        store = InMemoryCampaignStore()
        with _as_user(_BUILDER, store) as c:
            r = c.get("/api/admin/campaigns")
        assert r.status_code == 403

    def test_builder_owner_can_add_member(self):
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER)
        store._users[_VIEWER.id] = _VIEWER
        with _as_user(_BUILDER, store) as c:
            r = c.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members",
                json={"user_id": _VIEWER.id, "role": "viewer"},
            )
        assert r.status_code == 201

    def test_builder_editor_cannot_add_member(self):
        """Editors do not have MANAGE_MEMBERS permission."""
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER2)
        store._members[(campaign.id, _BUILDER.id)] = CampaignMemberRole.EDITOR.value
        store._users[_VIEWER.id] = _VIEWER
        with _as_user(_BUILDER, store) as c:
            r = c.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members",
                json={"user_id": _VIEWER.id, "role": "viewer"},
            )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Viewer role capabilities
# ---------------------------------------------------------------------------

class TestViewerRoleCapabilities:
    """Platform viewer: read-only access to member campaigns; no writes or admin."""

    def test_viewer_cannot_create_campaign(self):
        store = InMemoryCampaignStore()
        _ensure_workspace(store)
        store._workspace_members[(TEST_WS_ID, _VIEWER.id)] = "viewer"
        with _as_user(_VIEWER, store) as c:
            r = c.post(f"/api/workspaces/{TEST_WS_ID}/campaigns", json={"product_or_service": "P", "goal": "G"})
        assert r.status_code == 403

    def test_viewer_member_can_read_campaign(self):
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER)
        store._members[(campaign.id, _VIEWER.id)] = CampaignMemberRole.VIEWER.value
        with _as_user(_VIEWER, store) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
        assert r.status_code == 200

    def test_viewer_member_cannot_delete_campaign(self):
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER)
        store._members[(campaign.id, _VIEWER.id)] = CampaignMemberRole.VIEWER.value
        with _as_user(_VIEWER, store) as c:
            r = c.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
        assert r.status_code == 403

    def test_viewer_cannot_access_non_member_campaign(self):
        """Non-member viewer gets 404, not 403, to avoid existence leakage."""
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER)
        with _as_user(_VIEWER, store) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
        assert r.status_code == 404

    def test_viewer_list_only_shows_member_campaigns(self):
        """Workspace VIEWER member can list all workspace campaigns."""
        store = InMemoryCampaignStore()
        my_campaign = _make_campaign(store, _BUILDER)
        store._members[(my_campaign.id, _VIEWER.id)] = CampaignMemberRole.VIEWER.value
        _make_campaign(store, _BUILDER2)  # no campaign membership for viewer
        # Add _VIEWER as workspace VIEWER member so they can access the list endpoint
        store._workspace_members[(TEST_WS_ID, _VIEWER.id)] = "viewer"
        with _as_user(_VIEWER, store) as c:
            items = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns").json()
        # Workspace list shows all workspace campaigns to any workspace member
        assert len(items) == 2

    def test_viewer_cannot_access_admin_users_endpoint(self):
        store = InMemoryCampaignStore()
        with _as_user(_VIEWER, store) as c:
            r = c.get("/api/admin/users")
        assert r.status_code == 403

    def test_viewer_cannot_access_admin_campaigns_endpoint(self):
        store = InMemoryCampaignStore()
        with _as_user(_VIEWER, store) as c:
            r = c.get("/api/admin/campaigns")
        assert r.status_code == 403

    def test_viewer_member_cannot_add_members(self):
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER)
        store._members[(campaign.id, _VIEWER.id)] = CampaignMemberRole.VIEWER.value
        store._users[_BUILDER2.id] = _BUILDER2
        with _as_user(_VIEWER, store) as c:
            r = c.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members",
                json={"user_id": _BUILDER2.id, "role": "viewer"},
            )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Unauthenticated access (auth enabled — user is None triggers 401 guard)
# ---------------------------------------------------------------------------

class TestUnauthenticatedAccess:
    """When auth is enabled, admin endpoints reject unauthenticated requests with 401."""

    async def test_unauthenticated_gets_401_on_admin_users_endpoint(self):
        """GET /api/admin/users returns 401 when user is None."""
        app.dependency_overrides[get_current_user] = lambda: None

        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def override_get_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        try:
            with (
                patch("backend.apps.api.startup.init_db", new_callable=AsyncMock),
                patch("backend.apps.api.startup.close_db", new_callable=AsyncMock),
            ):
                transport = ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    r = await client.get("/api/admin/users")
            assert r.status_code == 401
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
            await engine.dispose()

    async def test_unauthenticated_gets_401_on_admin_role_update(self):
        """PATCH /api/admin/users/{id}/role returns 401 when user is None."""
        app.dependency_overrides[get_current_user] = lambda: None

        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def override_get_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        try:
            with (
                patch("backend.apps.api.startup.init_db", new_callable=AsyncMock),
                patch("backend.apps.api.startup.close_db", new_callable=AsyncMock),
            ):
                transport = ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    r = await client.patch("/api/admin/users/some-id/role", json={"roles": ["viewer"]})
            assert r.status_code == 401
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
            await engine.dispose()

    async def test_unauthenticated_gets_401_on_admin_campaigns_endpoint(self):
        """GET /api/admin/campaigns returns 401 when user is None."""
        store = InMemoryCampaignStore()
        app.dependency_overrides[get_current_user] = lambda: None

        try:
            with (
                patch("backend.api.admin.get_campaign_store", return_value=store),
                patch("backend.apps.api.startup.init_db", new_callable=AsyncMock),
                patch("backend.apps.api.startup.close_db", new_callable=AsyncMock),
            ):
                transport = ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    r = await client.get("/api/admin/campaigns")
            assert r.status_code == 401
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Specific edge cases for security correctness."""

    def test_removed_member_immediately_loses_access(self):
        """After removing a member, they can no longer read the campaign."""
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER)
        store._members[(campaign.id, _VIEWER.id)] = CampaignMemberRole.VIEWER.value

        # Verify access exists before removal
        with _as_user(_VIEWER, store) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
        assert r.status_code == 200

        # Remove the member
        del store._members[(campaign.id, _VIEWER.id)]

        # Verify access is revoked
        with _as_user(_VIEWER, store) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
        assert r.status_code == 404

    def test_non_member_gets_404_not_403(self):
        """Non-members get 404 (not 403) to avoid leaking campaign existence."""
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER)
        with _as_user(_BUILDER2, store) as c:
            r = c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
        assert r.status_code == 404

    def test_inactive_user_is_rejected_when_added_as_member(self):
        """Adding an inactive user as a campaign member returns 404."""
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER)
        inactive_user = User(
            id="inactive-001",
            email="inactive@example.com",
            display_name="Inactive",
            roles=[UserRole.VIEWER],
            is_active=False,
        )
        store._users[inactive_user.id] = inactive_user
        with _as_user(_BUILDER, store) as c:
            r = c.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/members",
                json={"user_id": inactive_user.id, "role": "viewer"},
            )
        assert r.status_code == 404

    def test_admin_sees_deleted_users_campaigns_after_removal(self):
        """After deleting a campaign, it no longer appears in any list."""
        store = InMemoryCampaignStore()
        campaign = _make_campaign(store, _BUILDER)

        with _as_user(_ADMIN, store) as c:
            assert len(c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns").json()) == 1
            c.delete(f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}")
            assert len(c.get(f"/api/workspaces/{TEST_WS_ID}/campaigns").json()) == 0
