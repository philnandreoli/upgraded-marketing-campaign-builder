"""
Tests for the campaign REST API routes.

Uses FastAPI's TestClient (synchronous) to test all endpoints.
The coordinator's pipeline is mocked so these run offline and don't hang.
The in-memory async store replaces the PostgreSQL-backed store so no
database is required.
"""

import pytest
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.campaign import Campaign, CampaignBrief
from backend.models.user import User, UserRole
from backend.services.auth import get_current_user
from backend.tests.mock_store import InMemoryCampaignStore

_TEST_USER = User(
    id="test-user-001",
    email="test@example.com",
    display_name="Test User",
    role=UserRole.CAMPAIGN_BUILDER,
)
_OTHER_USER = User(
    id="other-user-999",
    email="other@example.com",
    display_name="Other User",
    role=UserRole.CAMPAIGN_BUILDER,
)


@pytest.fixture(autouse=True)
def _isolated_store():
    """Give each test a fresh InMemoryCampaignStore and mock the pipeline."""
    fresh_store = InMemoryCampaignStore()

    # Mock _run_pipeline to be a no-op so BackgroundTasks doesn't trigger real LLM calls
    # Mock init_db/close_db so TestClient doesn't need a real database
    with patch("backend.api.campaigns.get_campaign_store", return_value=fresh_store), \
         patch("backend.api.campaigns._coordinator", None), \
         patch("backend.api.campaigns._run_pipeline", new_callable=AsyncMock), \
         patch("backend.main.init_db", new_callable=AsyncMock), \
         patch("backend.main.close_db", new_callable=AsyncMock):
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
        assert data["status"] == "healthy"
        assert "version" in data


# ---- POST /api/campaigns ----

class TestCreateCampaign:
    def test_create_returns_201(self, authed_client):
        r = authed_client.post("/api/campaigns", json={
            "product_or_service": "TestProduct",
            "goal": "Increase signups",
        })
        assert r.status_code == 201
        data = r.json()
        assert "id" in data
        assert data["status"] == "draft"

    def test_create_with_full_brief(self, authed_client):
        r = authed_client.post("/api/campaigns", json={
            "product_or_service": "CloudSync",
            "goal": "Grow enterprise",
            "budget": 50000,
            "currency": "EUR",
            "timeline": "3 months",
            "additional_context": "Focus on EMEA",
        })
        assert r.status_code == 201
        assert "id" in r.json()

    def test_create_with_selected_channels(self, authed_client):
        r = authed_client.post("/api/campaigns", json={
            "product_or_service": "ChannelTest",
            "goal": "Test channels",
            "selected_channels": ["email", "paid_ads"],
        })
        assert r.status_code == 201
        cid = r.json()["id"]
        detail = authed_client.get(f"/api/campaigns/{cid}").json()
        assert detail["brief"]["selected_channels"] == ["email", "paid_ads"]

    def test_create_with_invalid_channel_returns_422(self, authed_client):
        r = authed_client.post("/api/campaigns", json={
            "product_or_service": "BadChannel",
            "goal": "Test",
            "selected_channels": ["carrier_pigeon"],
        })
        assert r.status_code == 422

    def test_create_missing_required_field(self, authed_client):
        r = authed_client.post("/api/campaigns", json={
            "goal": "Missing product field",
        })
        assert r.status_code == 422  # Validation error

    def test_create_empty_body(self, authed_client):
        r = authed_client.post("/api/campaigns", json={})
        assert r.status_code == 422

    def test_create_viewer_returns_403(self, _isolated_store):
        """A viewer cannot create campaigns."""
        viewer = User(id="viewer-001", email="v@example.com", display_name="Viewer", role=UserRole.VIEWER)
        with _as_user(viewer) as c:
            r = c.post("/api/campaigns", json={
                "product_or_service": "Test", "goal": "Test",
            })
            assert r.status_code == 403

    def test_create_unauthenticated_allowed_when_auth_disabled(self, client):
        """When auth is disabled (user is None / dev mode), campaign creation is allowed."""
        r = client.post("/api/campaigns", json={
            "product_or_service": "Test", "goal": "Test",
        })
        assert r.status_code == 201

    def test_create_stores_owner_id(self, authed_client, _isolated_store):
        r = authed_client.post("/api/campaigns", json={
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
        r = client.get("/api/campaigns")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_after_create(self, authed_client):
        authed_client.post("/api/campaigns", json={
            "product_or_service": "A", "goal": "B",
        })
        authed_client.post("/api/campaigns", json={
            "product_or_service": "C", "goal": "D",
        })
        r = authed_client.get("/api/campaigns")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 2
        # Verify summary fields
        assert "id" in items[0]
        assert "status" in items[0]
        assert "product_or_service" in items[0]
        assert "goal" in items[0]
        assert "created_at" in items[0]

    def test_list_scoped_to_owner(self, _isolated_store):
        """Each authenticated user only sees their own campaigns."""
        # Directly insert campaigns with different owners (no async needed)
        my_campaign = Campaign(
            brief=CampaignBrief(product_or_service="My Campaign", goal="Mine"),
            owner_id=_TEST_USER.id,
        )
        their_campaign = Campaign(
            brief=CampaignBrief(product_or_service="Their Campaign", goal="Theirs"),
            owner_id=_OTHER_USER.id,
        )
        _isolated_store._campaigns.update({my_campaign.id: my_campaign, their_campaign.id: their_campaign})
        # Also add corresponding membership entries so list_accessible works correctly
        _isolated_store._members[(my_campaign.id, _TEST_USER.id)] = "owner"
        _isolated_store._members[(their_campaign.id, _OTHER_USER.id)] = "owner"

        with _as_user(_TEST_USER) as c:
            items = c.get("/api/campaigns").json()
            assert len(items) == 1
            assert items[0]["product_or_service"] == "My Campaign"

        with _as_user(_OTHER_USER) as c:
            items = c.get("/api/campaigns").json()
            assert len(items) == 1
            assert items[0]["product_or_service"] == "Their Campaign"


# ---- GET /api/campaigns/{id} ----

class TestGetCampaign:
    def test_get_existing(self, authed_client):
        r = authed_client.post("/api/campaigns", json={
            "product_or_service": "Test", "goal": "Test",
        })
        cid = r.json()["id"]
        r = authed_client.get(f"/api/campaigns/{cid}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == cid
        assert data["brief"]["product_or_service"] == "Test"

    def test_get_not_found(self, client):
        r = client.get("/api/campaigns/nonexistent-id")
        assert r.status_code == 404

    def test_get_other_user_campaign_returns_404(self, authed_client, _isolated_store):
        """A campaign created by user A should not be visible to user B."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Private", goal="Mine"),
            owner_id=_TEST_USER.id,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        with _as_user(_OTHER_USER) as c:
            r = c.get(f"/api/campaigns/{campaign.id}")
            assert r.status_code == 404


# ---- DELETE /api/campaigns/{id} ----

class TestDeleteCampaign:
    def test_delete_existing(self, authed_client):
        r = authed_client.post("/api/campaigns", json={
            "product_or_service": "Del", "goal": "Me",
        })
        cid = r.json()["id"]
        r = authed_client.delete(f"/api/campaigns/{cid}")
        assert r.status_code == 204

        # Confirm it's gone
        r = authed_client.get(f"/api/campaigns/{cid}")
        assert r.status_code == 404

    def test_delete_not_found(self, client):
        r = client.delete("/api/campaigns/nonexistent-id")
        assert r.status_code == 404

    def test_delete_other_user_campaign_returns_404(self, _isolated_store):
        """A user cannot delete another user's campaign."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Protected", goal="Mine"),
            owner_id=_TEST_USER.id,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        with _as_user(_OTHER_USER) as c:
            r = c.delete(f"/api/campaigns/{campaign.id}")
            assert r.status_code == 404


# ---- POST /api/campaigns/{id}/review (deprecated) ----

class TestSubmitReviewDeprecated:
    def test_review_returns_410(self, authed_client):
        """Legacy review endpoint should return 410 Gone."""
        r = authed_client.post("/api/campaigns", json={
            "product_or_service": "Rev", "goal": "Test",
        })
        cid = r.json()["id"]
        r = authed_client.post(f"/api/campaigns/{cid}/review", json={
            "campaign_id": cid,
            "approved": True,
            "notes": "Looks good",
        })
        assert r.status_code == 410


# ---- POST /api/campaigns/{id}/content-approve ----

class TestSubmitContentApproval:
    def test_content_approve_not_found(self, client):
        r = client.post("/api/campaigns/nonexistent-id/content-approve", json={
            "campaign_id": "nonexistent-id",
            "pieces": [],
        })
        assert r.status_code == 404

    def test_content_approve_missing_body(self, authed_client):
        r = authed_client.post("/api/campaigns", json={
            "product_or_service": "Appr", "goal": "Test",
        })
        cid = r.json()["id"]
        r = authed_client.post(f"/api/campaigns/{cid}/content-approve", json={})
        assert r.status_code == 422

    def test_content_approve_valid(self, authed_client):
        """Submit content approval for an existing campaign.
        The coordinator may not have a pending future, but the endpoint should not crash."""
        r = authed_client.post("/api/campaigns", json={
            "product_or_service": "Appr", "goal": "Test",
        })
        cid = r.json()["id"]
        r = authed_client.post(f"/api/campaigns/{cid}/content-approve", json={
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
        r = authed_client.post("/api/campaigns", json={
            "product_or_service": "RejCamp", "goal": "Test",
        })
        cid = r.json()["id"]
        r = authed_client.post(f"/api/campaigns/{cid}/content-approve", json={
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
        )
        _isolated_store._campaigns[campaign.id] = campaign
        with _as_user(_OTHER_USER) as c:
            r = c.post(f"/api/campaigns/{campaign.id}/content-approve", json={
                "campaign_id": campaign.id,
                "pieces": [],
                "reject_campaign": False,
            })
            assert r.status_code == 404


# ---- Convenience auth dependencies ----

class TestAuthDependencies:
    """Tests for require_authenticated, require_campaign_builder, require_admin."""

    async def test_require_authenticated_passes_for_user(self):
        """require_authenticated returns the user when one is present."""
        from backend.services.auth import require_authenticated

        result = await require_authenticated(_TEST_USER)
        assert result == _TEST_USER

    async def test_require_authenticated_raises_401_for_none(self):
        """require_authenticated raises 401 when user is None (auth disabled)."""
        from fastapi import HTTPException
        from backend.services.auth import require_authenticated

        with pytest.raises(HTTPException) as exc_info:
            await require_authenticated(None)
        assert exc_info.value.status_code == 401

    async def test_require_campaign_builder_passes_for_builder(self):
        """require_campaign_builder passes for campaign_builder role."""
        from backend.services.auth import require_campaign_builder

        result = await require_campaign_builder(_TEST_USER)
        assert result == _TEST_USER

    async def test_require_campaign_builder_passes_for_admin(self):
        """require_campaign_builder passes for admin role."""
        from backend.services.auth import require_campaign_builder

        admin_user = User(id="admin-001", email="admin@example.com", display_name="Admin", role=UserRole.ADMIN)
        result = await require_campaign_builder(admin_user)
        assert result == admin_user

    async def test_require_campaign_builder_raises_403_for_viewer(self):
        """require_campaign_builder raises 403 for viewer role."""
        from fastapi import HTTPException
        from backend.services.auth import require_campaign_builder

        viewer = User(id="viewer-001", email="viewer@example.com", display_name="Viewer", role=UserRole.VIEWER)
        with pytest.raises(HTTPException) as exc_info:
            await require_campaign_builder(viewer)
        assert exc_info.value.status_code == 403

    async def test_require_campaign_builder_raises_401_for_none(self):
        """require_campaign_builder raises 401 when user is None."""
        from fastapi import HTTPException
        from backend.services.auth import require_campaign_builder

        with pytest.raises(HTTPException) as exc_info:
            await require_campaign_builder(None)
        assert exc_info.value.status_code == 401

    async def test_require_admin_passes_for_admin(self):
        """require_admin passes for admin role."""
        from backend.services.auth import require_admin

        admin_user = User(id="admin-001", email="admin@example.com", display_name="Admin", role=UserRole.ADMIN)
        result = await require_admin(admin_user)
        assert result == admin_user

    async def test_require_admin_raises_403_for_campaign_builder(self):
        """require_admin raises 403 for campaign_builder role."""
        from fastapi import HTTPException
        from backend.services.auth import require_admin

        with pytest.raises(HTTPException) as exc_info:
            await require_admin(_TEST_USER)
        assert exc_info.value.status_code == 403

    async def test_require_admin_raises_403_for_viewer(self):
        """require_admin raises 403 for viewer role."""
        from fastapi import HTTPException
        from backend.services.auth import require_admin

        viewer = User(id="viewer-001", email="viewer@example.com", display_name="Viewer", role=UserRole.VIEWER)
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(viewer)
        assert exc_info.value.status_code == 403

    async def test_require_admin_raises_401_for_none(self):
        """require_admin raises 401 when user is None."""
        from fastapi import HTTPException
        from backend.services.auth import require_admin

        with pytest.raises(HTTPException) as exc_info:
            await require_admin(None)
        assert exc_info.value.status_code == 401


# ---- RBAC Authorization Matrix ----

_ADMIN_USER = User(id="admin-rbac-001", email="admin@example.com", display_name="Admin", role=UserRole.ADMIN)
_VIEWER_USER = User(id="viewer-rbac-001", email="viewer@example.com", display_name="Viewer", role=UserRole.VIEWER)


class TestAuthorizeFunction:
    """Tests for the _authorize helper covering the full RBAC matrix."""

    async def test_none_user_allows_all(self, _isolated_store):
        """Auth disabled (user=None) allows all actions."""
        from backend.api.campaigns import _authorize, Action
        campaign = Campaign(brief=CampaignBrief(product_or_service="X", goal="Y"), owner_id=None)
        _isolated_store._campaigns[campaign.id] = campaign
        for action in Action:
            await _authorize(campaign.id, None, action, _isolated_store)  # no exception

    async def test_admin_allows_all(self, _isolated_store):
        """Admin user can perform any action regardless of membership."""
        from backend.api.campaigns import _authorize, Action
        campaign = Campaign(brief=CampaignBrief(product_or_service="X", goal="Y"), owner_id="other")
        _isolated_store._campaigns[campaign.id] = campaign
        # admin has no membership — should still be allowed
        for action in Action:
            await _authorize(campaign.id, _ADMIN_USER, action, _isolated_store)  # no exception

    async def test_campaign_builder_owner_allows_all(self, _isolated_store):
        """campaign_builder with owner membership can perform all actions."""
        from backend.api.campaigns import _authorize, Action
        campaign = Campaign(brief=CampaignBrief(product_or_service="X", goal="Y"), owner_id=_TEST_USER.id)
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _TEST_USER.id)] = "owner"
        for action in Action:
            await _authorize(campaign.id, _TEST_USER, action, _isolated_store)  # no exception

    async def test_campaign_builder_editor_allows_read_write(self, _isolated_store):
        """campaign_builder with editor membership can READ and WRITE only."""
        from backend.api.campaigns import _authorize, Action
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
        from backend.api.campaigns import _authorize, Action
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
        from backend.api.campaigns import _authorize, Action
        from fastapi import HTTPException
        campaign = Campaign(brief=CampaignBrief(product_or_service="X", goal="Y"), owner_id="other")
        _isolated_store._campaigns[campaign.id] = campaign
        # No membership entry added
        with pytest.raises(HTTPException) as exc:
            await _authorize(campaign.id, _TEST_USER, Action.READ, _isolated_store)
        assert exc.value.status_code == 404

    async def test_viewer_member_allows_read_only(self, _isolated_store):
        """Platform viewer with any membership can only READ."""
        from backend.api.campaigns import _authorize, Action
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
        from backend.api.campaigns import _authorize, Action
        from fastapi import HTTPException
        campaign = Campaign(brief=CampaignBrief(product_or_service="X", goal="Y"), owner_id="other")
        _isolated_store._campaigns[campaign.id] = campaign
        with pytest.raises(HTTPException) as exc:
            await _authorize(campaign.id, _VIEWER_USER, Action.READ, _isolated_store)
        assert exc.value.status_code == 404


class TestRBACRoutes:
    """Integration tests for RBAC enforcement on campaign endpoints."""

    def test_editor_can_read_campaign(self, _isolated_store):
        """An editor member can GET a campaign."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Collab", goal="Work"),
            owner_id=_TEST_USER.id,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _OTHER_USER.id)] = "editor"
        with _as_user(_OTHER_USER) as c:
            r = c.get(f"/api/campaigns/{campaign.id}")
            assert r.status_code == 200

    def test_editor_cannot_delete_campaign(self, _isolated_store):
        """An editor member cannot DELETE a campaign."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Protected", goal="Mine"),
            owner_id=_TEST_USER.id,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _OTHER_USER.id)] = "editor"
        with _as_user(_OTHER_USER) as c:
            r = c.delete(f"/api/campaigns/{campaign.id}")
            assert r.status_code == 403

    def test_viewer_member_can_read_campaign(self, _isolated_store):
        """A platform viewer with membership can GET a campaign."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Shared", goal="View"),
            owner_id=_TEST_USER.id,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _VIEWER_USER.id)] = "viewer"
        with _as_user(_VIEWER_USER) as c:
            r = c.get(f"/api/campaigns/{campaign.id}")
            assert r.status_code == 200

    def test_viewer_member_cannot_delete_campaign(self, _isolated_store):
        """A platform viewer cannot DELETE even if they are a member."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Shared", goal="View"),
            owner_id=_TEST_USER.id,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _VIEWER_USER.id)] = "viewer"
        with _as_user(_VIEWER_USER) as c:
            r = c.delete(f"/api/campaigns/{campaign.id}")
            assert r.status_code == 403

    def test_admin_can_access_any_campaign(self, _isolated_store):
        """An admin can GET any campaign without membership."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Secret", goal="Admin"),
            owner_id=_TEST_USER.id,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        # No membership entry for admin
        with _as_user(_ADMIN_USER) as c:
            r = c.get(f"/api/campaigns/{campaign.id}")
            assert r.status_code == 200

    def test_admin_can_delete_any_campaign(self, _isolated_store):
        """An admin can DELETE any campaign without membership."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Secret", goal="Admin"),
            owner_id=_TEST_USER.id,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        with _as_user(_ADMIN_USER) as c:
            r = c.delete(f"/api/campaigns/{campaign.id}")
            assert r.status_code == 204

    def test_no_member_gets_404_not_403(self, _isolated_store):
        """A non-member gets 404 (not 403) to avoid leaking campaign existence."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Hidden", goal="Private"),
            owner_id=_TEST_USER.id,
        )
        _isolated_store._campaigns[campaign.id] = campaign
        with _as_user(_OTHER_USER) as c:
            r = c.get(f"/api/campaigns/{campaign.id}")
            assert r.status_code == 404
