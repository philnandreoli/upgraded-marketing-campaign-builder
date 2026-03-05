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
from backend.models.campaign import Campaign, CampaignBrief, CampaignContent, CampaignStatus, ContentApprovalStatus, ContentPiece
from backend.models.user import User, UserRole
from backend.services.auth import get_current_user
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
            "start_date": "2026-04-01",
            "end_date": "2026-06-30",
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
        viewer = User(id="viewer-001", email="v@example.com", display_name="Viewer", roles=[UserRole.VIEWER])
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
        )
        _isolated_store._campaigns[campaign.id] = campaign
        return campaign

    def test_update_notes_on_approved_piece(self, client, _isolated_store):
        """Successfully update human_notes on an approved piece."""
        campaign = self._campaign_with_approved_piece(_isolated_store)
        r = client.patch(
            f"/api/campaigns/{campaign.id}/content/0/notes",
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
        r = client.patch("/api/campaigns/nonexistent/content/0/notes", json={"notes": "x"})
        assert r.status_code == 404

    def test_update_notes_piece_out_of_range(self, client, _isolated_store):
        """Returns 404 when the piece index is out of range."""
        campaign = self._campaign_with_approved_piece(_isolated_store)
        r = client.patch(
            f"/api/campaigns/{campaign.id}/content/99/notes",
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
        )
        _isolated_store._campaigns[campaign.id] = campaign
        r = client.patch(
            f"/api/campaigns/{campaign.id}/content/0/notes",
            json={"notes": "too early"},
        )
        assert r.status_code == 409

    def test_update_notes_no_content(self, client, _isolated_store):
        """Returns 404 when campaign has no content at all."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Empty", goal="Test"),
        )
        _isolated_store._campaigns[campaign.id] = campaign
        r = client.patch(
            f"/api/campaigns/{campaign.id}/content/0/notes",
            json={"notes": "nothing here"},
        )
        assert r.status_code == 404

    def test_update_notes_other_user_returns_404(self, _isolated_store):
        """A user cannot update notes for another user's campaign."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Priv", goal="Test"),
            owner_id=_TEST_USER.id,
            content=CampaignContent(pieces=[
                ContentPiece(content_type="cta", content="Click!", approval_status=ContentApprovalStatus.APPROVED),
            ]),
        )
        _isolated_store._campaigns[campaign.id] = campaign
        with _as_user(_OTHER_USER) as c:
            r = c.patch(
                f"/api/campaigns/{campaign.id}/content/0/notes",
                json={"notes": "sneaky"},
            )
            assert r.status_code == 404

class TestSubmitClarification:
    def test_clarify_not_found(self, client):
        """Returns 404 when the campaign does not exist."""
        r = client.post("/api/campaigns/nonexistent-id/clarify", json={
            "campaign_id": "nonexistent-id",
            "answers": {"q1": "answer"},
        })
        assert r.status_code == 404

    def test_clarify_wrong_status_returns_409(self, client, _isolated_store):
        """Returns 409 when the campaign is not in 'clarification' status."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Test", goal="Test"),
        )
        # Campaign starts in DRAFT status — not CLARIFICATION
        _isolated_store._campaigns[campaign.id] = campaign

        r = client.post(f"/api/campaigns/{campaign.id}/clarify", json={
            "campaign_id": campaign.id,
            "answers": {"q1": "answer"},
        })
        assert r.status_code == 409
        assert "clarification" in r.json()["detail"].lower()

    def test_clarify_valid(self, client, _isolated_store):
        """Accepts clarification answers when campaign is in 'clarification' status."""
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Test", goal="Test"),
        )
        campaign.advance_status(CampaignStatus.CLARIFICATION)
        _isolated_store._campaigns[campaign.id] = campaign

        with patch("backend.api.campaigns._get_coordinator") as mock_coord_fn:
            mock_coord = MagicMock()
            mock_coord.submit_clarification = AsyncMock()
            mock_coord_fn.return_value = mock_coord

            r = client.post(f"/api/campaigns/{campaign.id}/clarify", json={
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
        )
        campaign.advance_status(CampaignStatus.CLARIFICATION)
        _isolated_store._campaigns[campaign.id] = campaign
        _isolated_store._members[(campaign.id, _TEST_USER.id)] = "owner"

        with _as_user(_OTHER_USER) as c:
            r = c.post(f"/api/campaigns/{campaign.id}/clarify", json={
                "campaign_id": campaign.id,
                "answers": {"q1": "answer"},
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

        admin_user = User(id="admin-001", email="admin@example.com", display_name="Admin", roles=[UserRole.ADMIN])
        result = await require_campaign_builder(admin_user)
        assert result == admin_user

    async def test_require_campaign_builder_raises_403_for_viewer(self):
        """require_campaign_builder raises 403 for viewer role."""
        from fastapi import HTTPException
        from backend.services.auth import require_campaign_builder

        viewer = User(id="viewer-001", email="viewer@example.com", display_name="Viewer", roles=[UserRole.VIEWER])
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

        admin_user = User(id="admin-001", email="admin@example.com", display_name="Admin", roles=[UserRole.ADMIN])
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

        viewer = User(id="viewer-001", email="viewer@example.com", display_name="Viewer", roles=[UserRole.VIEWER])
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

_ADMIN_USER = User(id="admin-rbac-001", email="admin@example.com", display_name="Admin", roles=[UserRole.ADMIN])
_VIEWER_USER = User(id="viewer-rbac-001", email="viewer@example.com", display_name="Viewer", roles=[UserRole.VIEWER])


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


# ---- Member management endpoints ----

class TestCampaignMembers:
    """Tests for GET/POST/PATCH/DELETE /api/campaigns/{id}/members."""

    def _setup_campaign(self, store):
        """Helper: insert a campaign owned by _TEST_USER and return it."""
        from backend.models.user import User
        campaign = Campaign(
            brief=CampaignBrief(product_or_service="Team", goal="Collaborate"),
            owner_id=_TEST_USER.id,
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
            r = c.get(f"/api/campaigns/{campaign.id}/members")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["user_id"] == _TEST_USER.id
        assert data[0]["role"] == "owner"

    def test_list_members_campaign_not_found(self, client):
        r = client.get("/api/campaigns/nonexistent/members")
        assert r.status_code == 404

    def test_list_members_requires_read_access(self, _isolated_store):
        """A non-member gets 404 when listing members."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_OTHER_USER) as c:
            r = c.get(f"/api/campaigns/{campaign.id}/members")
        assert r.status_code == 404

    # ---- POST /members ----

    def test_add_member_success(self, _isolated_store):
        """Owner can add an editor member."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_TEST_USER) as c:
            r = c.post(f"/api/campaigns/{campaign.id}/members", json={
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
            r = c.post(f"/api/campaigns/{campaign.id}/members", json={
                "user_id": _OTHER_USER.id,
            })
        assert r.status_code == 201
        assert r.json()["role"] == "viewer"

    def test_add_member_rejects_owner_role(self, _isolated_store):
        """POST /members with role=owner is rejected with 422."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_TEST_USER) as c:
            r = c.post(f"/api/campaigns/{campaign.id}/members", json={
                "user_id": _OTHER_USER.id,
                "role": "owner",
            })
        assert r.status_code == 422

    def test_add_member_user_not_found(self, _isolated_store):
        """POST /members with unknown user_id returns 404."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_TEST_USER) as c:
            r = c.post(f"/api/campaigns/{campaign.id}/members", json={
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
            r = c.post(f"/api/campaigns/{campaign.id}/members", json={
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
        with _as_user(_OTHER_USER) as c:
            r = c.post(f"/api/campaigns/{campaign.id}/members", json={
                "user_id": third.id,
                "role": "viewer",
            })
        assert r.status_code == 403

    def test_add_member_campaign_not_found(self, _isolated_store):
        """POST /members on nonexistent campaign returns 404."""
        _isolated_store._users[_TEST_USER.id] = _TEST_USER
        with _as_user(_TEST_USER) as c:
            r = c.post("/api/campaigns/nonexistent/members", json={
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
            r = c.patch(f"/api/campaigns/{campaign.id}/members/{_OTHER_USER.id}", json={
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
            r = c.patch(f"/api/campaigns/{campaign.id}/members/{_OTHER_USER.id}", json={
                "role": "owner",
            })
        assert r.status_code == 422

    def test_patch_member_not_found(self, _isolated_store):
        """PATCH /members/{id} for non-member returns 404."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_TEST_USER) as c:
            r = c.patch(f"/api/campaigns/{campaign.id}/members/{_OTHER_USER.id}", json={
                "role": "editor",
            })
        assert r.status_code == 404

    def test_patch_member_user_not_in_system(self, _isolated_store):
        """PATCH /members/{id} with unknown user_id returns 404."""
        campaign = self._setup_campaign(_isolated_store)
        _isolated_store._members[(campaign.id, "unknown-user")] = "editor"
        with _as_user(_TEST_USER) as c:
            r = c.patch(f"/api/campaigns/{campaign.id}/members/unknown-user", json={
                "role": "viewer",
            })
        assert r.status_code == 404

    # ---- DELETE /members/{user_id} ----

    def test_delete_member_success(self, _isolated_store):
        """Owner can remove an editor member."""
        campaign = self._setup_campaign(_isolated_store)
        _isolated_store._members[(campaign.id, _OTHER_USER.id)] = "editor"
        with _as_user(_TEST_USER) as c:
            r = c.delete(f"/api/campaigns/{campaign.id}/members/{_OTHER_USER.id}")
        assert r.status_code == 204
        assert (campaign.id, _OTHER_USER.id) not in _isolated_store._members

    def test_delete_last_owner_returns_409(self, _isolated_store):
        """Cannot remove the last owner of a campaign."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_TEST_USER) as c:
            r = c.delete(f"/api/campaigns/{campaign.id}/members/{_TEST_USER.id}")
        assert r.status_code == 409

    def test_delete_member_not_found(self, _isolated_store):
        """DELETE /members/{id} for non-member returns 404."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_TEST_USER) as c:
            r = c.delete(f"/api/campaigns/{campaign.id}/members/{_OTHER_USER.id}")
        assert r.status_code == 404

    def test_delete_member_editor_cannot_manage_members(self, _isolated_store):
        """An editor cannot remove members."""
        campaign = self._setup_campaign(_isolated_store)
        _isolated_store._members[(campaign.id, _OTHER_USER.id)] = "editor"
        third = User(id="third-user", email="third@example.com", display_name="Third", roles=[UserRole.CAMPAIGN_BUILDER])
        _isolated_store._members[(campaign.id, third.id)] = "viewer"
        with _as_user(_OTHER_USER) as c:
            r = c.delete(f"/api/campaigns/{campaign.id}/members/{third.id}")
        assert r.status_code == 403

    def test_delete_non_last_owner_succeeds(self, _isolated_store):
        """Can remove one owner when another owner still exists."""
        campaign = self._setup_campaign(_isolated_store)
        _isolated_store._members[(campaign.id, _OTHER_USER.id)] = "owner"
        with _as_user(_TEST_USER) as c:
            r = c.delete(f"/api/campaigns/{campaign.id}/members/{_OTHER_USER.id}")
        assert r.status_code == 204

    def test_admin_can_manage_members_without_membership(self, _isolated_store):
        """Admin can add members to any campaign without being a member."""
        campaign = self._setup_campaign(_isolated_store)
        with _as_user(_ADMIN_USER) as c:
            r = c.post(f"/api/campaigns/{campaign.id}/members", json={
                "user_id": _OTHER_USER.id,
                "role": "editor",
            })
        assert r.status_code == 201
