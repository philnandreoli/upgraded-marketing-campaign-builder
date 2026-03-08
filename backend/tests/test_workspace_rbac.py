"""
Workspace-aware campaign authorization tests.

Tests the full campaign RBAC matrix when campaigns are associated with a
workspace, including precedence rules:

  admin > campaign_member > workspace_member > owner_id > 404

Matrix covered:
  Workspace Role  | Platform Role | Action  | Expected
  ----------------+---------------+---------+---------
  CREATOR         | builder       | READ    | allowed
  CREATOR         | builder       | WRITE   | allowed
  CREATOR         | builder       | DELETE  | allowed
  CONTRIBUTOR     | builder       | READ    | allowed
  CONTRIBUTOR     | builder       | WRITE   | allowed
  CONTRIBUTOR     | builder       | DELETE  | 403
  VIEWER          | builder       | READ    | allowed
  VIEWER          | builder       | WRITE   | 403
  campaign member | builder       | *       | campaign role wins
  CREATOR         | viewer        | WRITE   | 403 (platform viewer cap)
  orphaned (none) | builder       | READ    | 200 if owner
  orphaned (none) | builder       | READ    | 404 if not owner
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api.campaigns import Action, _authorize
from backend.main import app
from backend.models.campaign import Campaign, CampaignBrief
from backend.models.user import CampaignMemberRole, User, UserRole
from backend.models.workspace import Workspace, WorkspaceRole
from backend.services.auth import get_current_user
from backend.tests.mock_store import InMemoryCampaignStore


# ---------------------------------------------------------------------------
# Module-level users
# ---------------------------------------------------------------------------

_ADMIN = User(
    id="ws-rbac-admin-001",
    email="admin@wsrbac.test",
    display_name="Admin",
    roles=[UserRole.ADMIN],
)
_BUILDER = User(
    id="ws-rbac-builder-001",
    email="builder@wsrbac.test",
    display_name="Builder",
    roles=[UserRole.CAMPAIGN_BUILDER],
)
_BUILDER2 = User(
    id="ws-rbac-builder-002",
    email="builder2@wsrbac.test",
    display_name="Builder2",
    roles=[UserRole.CAMPAIGN_BUILDER],
)
_VIEWER = User(
    id="ws-rbac-viewer-001",
    email="viewer@wsrbac.test",
    display_name="Viewer",
    roles=[UserRole.VIEWER],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_workspace_store(
    user: User,
    ws_role: WorkspaceRole | None,
    campaign_member_role: CampaignMemberRole | None = None,
    campaign_owner: User | None = None,
) -> tuple[InMemoryCampaignStore, Campaign]:
    """Build an in-memory store with a workspace and campaign, then set up memberships."""
    store = InMemoryCampaignStore()
    ws_id = "test-ws-001"
    store._workspaces[ws_id] = Workspace(
        id=ws_id,
        name="Test Workspace",
        owner_id="owner-001",
        is_personal=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    owner_id = campaign_owner.id if campaign_owner else "campaign-owner-001"
    campaign = Campaign(
        brief=CampaignBrief(product_or_service="RBAC Test", goal="Test workspace RBAC"),
        owner_id=owner_id,
        workspace_id=ws_id,
    )
    store._campaigns[campaign.id] = campaign

    if ws_role is not None:
        store._workspace_members[(ws_id, user.id)] = ws_role.value

    if campaign_member_role is not None:
        store._members[(campaign.id, user.id)] = campaign_member_role.value

    return store, campaign


@contextmanager
def _as_user(user: User, store: InMemoryCampaignStore):
    """TestClient context with *user* as the authenticated principal."""
    app.dependency_overrides[get_current_user] = lambda: user
    mock_executor = MagicMock()
    mock_executor.dispatch = AsyncMock()
    try:
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
            yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Direct _authorize unit tests — workspace CREATOR
# ---------------------------------------------------------------------------

class TestWorkspaceCreatorCampaignAccess:
    """Workspace CREATOR can read, write, and delete campaigns in the workspace."""

    async def test_creator_can_read_campaign_in_workspace(self):
        store, campaign = _make_workspace_store(_BUILDER, WorkspaceRole.CREATOR)
        # Should not raise
        await _authorize(campaign.id, _BUILDER, Action.READ, store)

    async def test_creator_can_write_campaign_in_workspace(self):
        store, campaign = _make_workspace_store(_BUILDER, WorkspaceRole.CREATOR)
        await _authorize(campaign.id, _BUILDER, Action.WRITE, store)

    async def test_creator_can_delete_campaign_in_workspace(self):
        store, campaign = _make_workspace_store(_BUILDER, WorkspaceRole.CREATOR)
        await _authorize(campaign.id, _BUILDER, Action.DELETE, store)

    async def test_creator_can_manage_members_of_campaign_in_workspace(self):
        store, campaign = _make_workspace_store(_BUILDER, WorkspaceRole.CREATOR)
        await _authorize(campaign.id, _BUILDER, Action.MANAGE_MEMBERS, store)


# ---------------------------------------------------------------------------
# Direct _authorize unit tests — workspace CONTRIBUTOR
# ---------------------------------------------------------------------------

class TestWorkspaceContributorCampaignAccess:
    """Workspace CONTRIBUTOR can read and write but cannot delete."""

    async def test_contributor_can_read_campaign_in_workspace(self):
        store, campaign = _make_workspace_store(_BUILDER, WorkspaceRole.CONTRIBUTOR)
        await _authorize(campaign.id, _BUILDER, Action.READ, store)

    async def test_contributor_can_write_campaign_in_workspace(self):
        store, campaign = _make_workspace_store(_BUILDER, WorkspaceRole.CONTRIBUTOR)
        await _authorize(campaign.id, _BUILDER, Action.WRITE, store)

    async def test_contributor_cannot_delete_campaign_in_workspace(self):
        store, campaign = _make_workspace_store(_BUILDER, WorkspaceRole.CONTRIBUTOR)
        with pytest.raises(HTTPException) as exc_info:
            await _authorize(campaign.id, _BUILDER, Action.DELETE, store)
        assert exc_info.value.status_code == 403

    async def test_contributor_cannot_manage_members_of_campaign(self):
        store, campaign = _make_workspace_store(_BUILDER, WorkspaceRole.CONTRIBUTOR)
        with pytest.raises(HTTPException) as exc_info:
            await _authorize(campaign.id, _BUILDER, Action.MANAGE_MEMBERS, store)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Direct _authorize unit tests — workspace VIEWER
# ---------------------------------------------------------------------------

class TestWorkspaceViewerCampaignAccess:
    """Workspace VIEWER can only read campaigns."""

    async def test_viewer_can_read_campaign_in_workspace(self):
        store, campaign = _make_workspace_store(_BUILDER, WorkspaceRole.VIEWER)
        await _authorize(campaign.id, _BUILDER, Action.READ, store)

    async def test_viewer_cannot_write_campaign_in_workspace(self):
        store, campaign = _make_workspace_store(_BUILDER, WorkspaceRole.VIEWER)
        with pytest.raises(HTTPException) as exc_info:
            await _authorize(campaign.id, _BUILDER, Action.WRITE, store)
        assert exc_info.value.status_code == 403

    async def test_viewer_cannot_delete_campaign_in_workspace(self):
        store, campaign = _make_workspace_store(_BUILDER, WorkspaceRole.VIEWER)
        with pytest.raises(HTTPException) as exc_info:
            await _authorize(campaign.id, _BUILDER, Action.DELETE, store)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Campaign member role takes precedence over workspace role
# ---------------------------------------------------------------------------

class TestCampaignMemberPrecedence:
    """Direct campaign membership overrides workspace membership."""

    async def test_campaign_editor_member_overrides_workspace_viewer(self):
        """EDITOR campaign membership → WRITE allowed, even with ws VIEWER role."""
        store, campaign = _make_workspace_store(
            _BUILDER,
            ws_role=WorkspaceRole.VIEWER,
            campaign_member_role=CampaignMemberRole.EDITOR,
        )
        # Campaign EDITOR can write (workspace VIEWER alone would deny this)
        await _authorize(campaign.id, _BUILDER, Action.WRITE, store)

    async def test_campaign_viewer_member_overrides_workspace_creator(self):
        """VIEWER campaign membership → DELETE denied, even with ws CREATOR role."""
        store, campaign = _make_workspace_store(
            _BUILDER,
            ws_role=WorkspaceRole.CREATOR,
            campaign_member_role=CampaignMemberRole.VIEWER,
        )
        with pytest.raises(HTTPException) as exc_info:
            await _authorize(campaign.id, _BUILDER, Action.DELETE, store)
        assert exc_info.value.status_code == 403

    async def test_campaign_owner_member_gets_full_access_regardless_of_workspace(self):
        """OWNER campaign membership → full access, even without any workspace role."""
        store, campaign = _make_workspace_store(
            _BUILDER,
            ws_role=None,
            campaign_member_role=CampaignMemberRole.OWNER,
        )
        await _authorize(campaign.id, _BUILDER, Action.DELETE, store)


# ---------------------------------------------------------------------------
# Platform VIEWER role cap
# ---------------------------------------------------------------------------

class TestPlatformViewerOverride:
    """Platform VIEWER role is always capped at READ regardless of workspace role."""

    async def test_platform_viewer_overrides_workspace_creator(self):
        """A platform VIEWER with workspace CREATOR role still cannot delete."""
        store, campaign = _make_workspace_store(_VIEWER, WorkspaceRole.CREATOR)
        with pytest.raises(HTTPException) as exc_info:
            await _authorize(campaign.id, _VIEWER, Action.DELETE, store)
        assert exc_info.value.status_code == 403

    async def test_platform_viewer_with_workspace_creator_cannot_write(self):
        """Platform VIEWER is capped at READ even with ws CREATOR."""
        store, campaign = _make_workspace_store(_VIEWER, WorkspaceRole.CREATOR)
        with pytest.raises(HTTPException) as exc_info:
            await _authorize(campaign.id, _VIEWER, Action.WRITE, store)
        assert exc_info.value.status_code == 403

    async def test_platform_viewer_with_workspace_creator_can_read(self):
        """Platform VIEWER with workspace CREATOR role can still READ."""
        store, campaign = _make_workspace_store(_VIEWER, WorkspaceRole.CREATOR)
        await _authorize(campaign.id, _VIEWER, Action.READ, store)


# ---------------------------------------------------------------------------
# Orphaned campaign (no workspace_id) — owner_id fallback
# ---------------------------------------------------------------------------

class TestOrphanedCampaign:
    """Campaigns without a workspace_id fall back to owner_id access."""

    async def test_orphaned_campaign_accessible_via_owner_id(self):
        """Campaign owner can still access orphaned (no workspace) campaign."""
        store = InMemoryCampaignStore()
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Orphan", goal="Test"),
            owner_id=_BUILDER.id,
            workspace_id=None,
        )
        store._campaigns[campaign.id] = campaign
        # No campaign membership, no workspace membership
        # Should still succeed because owner_id matches
        await _authorize(campaign.id, _BUILDER, Action.READ, store)

    async def test_non_owner_cannot_access_orphaned_campaign(self):
        """Non-owner with no membership gets 404 for an orphaned campaign."""
        store = InMemoryCampaignStore()
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Orphan", goal="Test"),
            owner_id=_BUILDER2.id,  # owned by someone else
            workspace_id=None,
        )
        store._campaigns[campaign.id] = campaign
        with pytest.raises(HTTPException) as exc_info:
            await _authorize(campaign.id, _BUILDER, Action.READ, store)
        assert exc_info.value.status_code == 404

    async def test_no_membership_anywhere_gets_404(self):
        """User with no campaign or workspace membership gets 404."""
        store = InMemoryCampaignStore()
        ws_id = "orphan-ws-001"
        store._workspaces[ws_id] = Workspace(
            id=ws_id,
            name="Some WS",
            owner_id="other",
            is_personal=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Hidden", goal="Test"),
            owner_id="other",
            workspace_id=ws_id,
        )
        store._campaigns[campaign.id] = campaign
        # _BUILDER is not a workspace member and not the owner
        with pytest.raises(HTTPException) as exc_info:
            await _authorize(campaign.id, _BUILDER, Action.READ, store)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# HTTP-level tests — admin moves campaign between workspaces
# ---------------------------------------------------------------------------

class TestAdminMoveCampaign:
    """PATCH /api/campaigns/{id}/workspace — admin-only endpoint."""

    def test_admin_can_move_campaign_between_workspaces(self):
        store = InMemoryCampaignStore()
        ws_a_id = "move-ws-a"
        ws_b_id = "move-ws-b"
        now = datetime.now(timezone.utc)
        store._workspaces[ws_a_id] = Workspace(
            id=ws_a_id, name="WS A", owner_id="owner",
            is_personal=False, created_at=now, updated_at=now,
        )
        store._workspaces[ws_b_id] = Workspace(
            id=ws_b_id, name="WS B", owner_id="owner",
            is_personal=False, created_at=now, updated_at=now,
        )
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Movable", goal="Move me"),
            owner_id=_BUILDER.id,
            workspace_id=ws_a_id,
        )
        store._campaigns[campaign.id] = campaign

        with _as_user(_ADMIN, store) as c:
            r = c.patch(
                f"/api/campaigns/{campaign.id}/workspace",
                json={"workspace_id": ws_b_id},
            )
        assert r.status_code == 200
        assert store._campaigns[campaign.id].workspace_id == ws_b_id

    def test_non_admin_cannot_move_campaign(self):
        store = InMemoryCampaignStore()
        ws_a_id = "move-ws-a"
        ws_b_id = "move-ws-b"
        now = datetime.now(timezone.utc)
        store._workspaces[ws_a_id] = Workspace(
            id=ws_a_id, name="WS A", owner_id=_BUILDER.id,
            is_personal=False, created_at=now, updated_at=now,
        )
        store._workspaces[ws_b_id] = Workspace(
            id=ws_b_id, name="WS B", owner_id=_BUILDER.id,
            is_personal=False, created_at=now, updated_at=now,
        )
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Movable", goal="Move me"),
            owner_id=_BUILDER.id,
            workspace_id=ws_a_id,
        )
        store._campaigns[campaign.id] = campaign
        store._workspace_members[(ws_a_id, _BUILDER.id)] = WorkspaceRole.CREATOR.value

        with _as_user(_BUILDER, store) as c:
            r = c.patch(
                f"/api/campaigns/{campaign.id}/workspace",
                json={"workspace_id": ws_b_id},
            )
        assert r.status_code == 403

    def test_admin_can_orphan_campaign(self):
        """Admin can set workspace_id to null, orphaning the campaign."""
        store = InMemoryCampaignStore()
        ws_id = "orphan-src-ws"
        now = datetime.now(timezone.utc)
        store._workspaces[ws_id] = Workspace(
            id=ws_id, name="WS", owner_id="owner",
            is_personal=False, created_at=now, updated_at=now,
        )
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Orphanable", goal="Orphan me"),
            owner_id=_BUILDER.id,
            workspace_id=ws_id,
        )
        store._campaigns[campaign.id] = campaign

        with _as_user(_ADMIN, store) as c:
            r = c.patch(
                f"/api/campaigns/{campaign.id}/workspace",
                json={"workspace_id": None},
            )
        assert r.status_code == 200
        assert store._campaigns[campaign.id].workspace_id is None


# ---------------------------------------------------------------------------
# HTTP-level tests — creating campaign in workspace requires CREATOR role
# ---------------------------------------------------------------------------

class TestCreateCampaignInWorkspace:
    """POST /api/campaigns with workspace_id — CREATOR-only."""

    def test_workspace_creator_can_create_campaign_in_workspace(self):
        store = InMemoryCampaignStore()
        ws_id = "create-ws-001"
        now = datetime.now(timezone.utc)
        store._workspaces[ws_id] = Workspace(
            id=ws_id, name="Create WS", owner_id=_BUILDER.id,
            is_personal=False, created_at=now, updated_at=now,
        )
        store._workspace_members[(ws_id, _BUILDER.id)] = WorkspaceRole.CREATOR.value

        with _as_user(_BUILDER, store) as c:
            r = c.post(
                "/api/campaigns",
                json={
                    "product_or_service": "New Product",
                    "goal": "Test goal",
                    "workspace_id": ws_id,
                },
            )
        assert r.status_code == 201

    def test_workspace_contributor_cannot_create_campaign_in_workspace(self):
        """CONTRIBUTOR cannot create a campaign in the workspace."""
        store = InMemoryCampaignStore()
        ws_id = "create-ws-001"
        now = datetime.now(timezone.utc)
        store._workspaces[ws_id] = Workspace(
            id=ws_id, name="Create WS", owner_id="owner",
            is_personal=False, created_at=now, updated_at=now,
        )
        store._workspace_members[(ws_id, _BUILDER.id)] = WorkspaceRole.CONTRIBUTOR.value

        with _as_user(_BUILDER, store) as c:
            r = c.post(
                "/api/campaigns",
                json={
                    "product_or_service": "New Product",
                    "goal": "Test goal",
                    "workspace_id": ws_id,
                },
            )
        assert r.status_code == 403

    def test_non_workspace_member_cannot_create_campaign_in_workspace(self):
        """Non-member cannot create a campaign in the workspace."""
        store = InMemoryCampaignStore()
        ws_id = "create-ws-001"
        now = datetime.now(timezone.utc)
        store._workspaces[ws_id] = Workspace(
            id=ws_id, name="Create WS", owner_id="owner",
            is_personal=False, created_at=now, updated_at=now,
        )

        with _as_user(_BUILDER, store) as c:
            r = c.post(
                "/api/campaigns",
                json={
                    "product_or_service": "New Product",
                    "goal": "Test goal",
                    "workspace_id": ws_id,
                },
            )
        assert r.status_code == 403

    def test_admin_can_create_campaign_in_any_workspace(self):
        """Admin bypasses workspace membership check for campaign creation."""
        store = InMemoryCampaignStore()
        ws_id = "create-ws-admin"
        now = datetime.now(timezone.utc)
        store._workspaces[ws_id] = Workspace(
            id=ws_id, name="Admin WS", owner_id="other",
            is_personal=False, created_at=now, updated_at=now,
        )

        with _as_user(_ADMIN, store) as c:
            r = c.post(
                "/api/campaigns",
                json={
                    "product_or_service": "Admin Product",
                    "goal": "Admin goal",
                    "workspace_id": ws_id,
                },
            )
        assert r.status_code == 201
