"""
Tests for campaign comment API endpoints.

Covers all 6 endpoints:
  POST   .../comments         — create
  GET    .../comments         — list (with section/piece_index filters)
  GET    .../comments/count   — unresolved count
  PATCH  .../comments/{id}    — update body (author-only)
  DELETE .../comments/{id}    — delete (author-only or admin)
  PATCH  .../comments/{id}/resolve — toggle resolve
"""

import asyncio
import pytest
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.models.campaign import Campaign, CampaignBrief, CampaignStatus, CommentSection
from backend.models.user import CampaignMemberRole, User, UserRole
from backend.models.workspace import Workspace, WorkspaceRole
from backend.infrastructure.auth import get_current_user
from backend.tests.mock_store import InMemoryCampaignStore, InMemoryCommentStore

from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Test actors
# ---------------------------------------------------------------------------

_OWNER = User(
    id="comment-owner-001",
    email="owner@test.com",
    display_name="Owner",
    roles=[UserRole.CAMPAIGN_BUILDER],
)
_EDITOR = User(
    id="comment-editor-001",
    email="editor@test.com",
    display_name="Editor",
    roles=[UserRole.CAMPAIGN_BUILDER],
)
_VIEWER = User(
    id="comment-viewer-001",
    email="viewer@test.com",
    display_name="Viewer",
    roles=[UserRole.CAMPAIGN_BUILDER],
)
_NON_MEMBER = User(
    id="comment-nonmember-001",
    email="nonmember@test.com",
    display_name="NonMember",
    roles=[UserRole.CAMPAIGN_BUILDER],
)
_ADMIN = User(
    id="comment-admin-001",
    email="admin@test.com",
    display_name="Admin",
    roles=[UserRole.ADMIN],
)

TEST_WS_ID = "test-ws-comments"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store_with_campaign() -> tuple[InMemoryCampaignStore, Campaign]:
    """Create an InMemoryCampaignStore pre-populated with a workspace and campaign."""
    store = InMemoryCampaignStore()
    store._workspaces[TEST_WS_ID] = Workspace(
        id=TEST_WS_ID,
        name="Test Workspace",
        owner_id=_OWNER.id,
        is_personal=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    store._workspace_members[(TEST_WS_ID, _OWNER.id)] = WorkspaceRole.CREATOR.value

    brief = CampaignBrief(product_or_service="Test Product", goal="Test Goal")
    campaign = Campaign(
        brief=brief,
        owner_id=_OWNER.id,
        workspace_id=TEST_WS_ID,
        status=CampaignStatus.STRATEGY,
    )
    store._campaigns[campaign.id] = campaign
    store._members[(campaign.id, _OWNER.id)] = CampaignMemberRole.OWNER.value
    store._members[(campaign.id, _EDITOR.id)] = CampaignMemberRole.EDITOR.value
    store._members[(campaign.id, _VIEWER.id)] = CampaignMemberRole.VIEWER.value

    for u in [_OWNER, _EDITOR, _VIEWER, _NON_MEMBER, _ADMIN]:
        store.add_user(u)

    return store, campaign


@contextmanager
def _as_user(user: User, store: InMemoryCampaignStore, comment_store: InMemoryCommentStore):
    """TestClient context with patched stores and auth."""
    app.dependency_overrides[get_current_user] = lambda: user
    mock_executor = MagicMock()
    mock_executor.dispatch = AsyncMock()
    try:
        with (
            patch("backend.api.campaigns.get_campaign_store", return_value=store),
            patch("backend.apps.api.dependencies.get_campaign_store", return_value=store),
            patch("backend.api.campaign_members.get_campaign_store", return_value=store),
            patch("backend.api.campaign_comments.get_comment_store", return_value=comment_store),
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
# POST .../comments
# ---------------------------------------------------------------------------

class TestCreateComment:
    """Tests for POST /api/workspaces/{ws}/campaigns/{cid}/comments."""

    def test_owner_can_create_comment(self):
        """201 when owner creates a comment."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()
        with _as_user(_OWNER, store, comment_store) as client:
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments",
                json={"body": "Great strategy!", "section": "strategy"},
            )
        assert r.status_code == 201
        data = r.json()
        assert data["body"] == "Great strategy!"
        assert data["section"] == "strategy"
        assert data["author_id"] == _OWNER.id
        assert data["campaign_id"] == campaign.id
        assert data["is_resolved"] is False

    def test_editor_can_create_comment(self):
        """201 when an editor creates a comment."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()
        with _as_user(_EDITOR, store, comment_store) as client:
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments",
                json={"body": "Looks good to me", "section": "content"},
            )
        assert r.status_code == 201
        assert r.json()["author_id"] == _EDITOR.id

    def test_viewer_cannot_create_comment(self):
        """403 when a viewer (READ-only) tries to create a comment."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()
        with _as_user(_VIEWER, store, comment_store) as client:
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments",
                json={"body": "I want to comment", "section": "strategy"},
            )
        assert r.status_code == 403

    def test_non_member_gets_404(self):
        """Non-members get 404 (consistent RBAC pattern)."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()
        with _as_user(_NON_MEMBER, store, comment_store) as client:
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments",
                json={"body": "Can I comment?", "section": "general"},
            )
        assert r.status_code == 404

    def test_empty_body_is_rejected(self):
        """422 when body text is empty."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()
        with _as_user(_OWNER, store, comment_store) as client:
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments",
                json={"body": "", "section": "strategy"},
            )
        assert r.status_code == 422

    def test_create_with_parent_and_piece_index(self):
        """201 with parent_id and content_piece_index set."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()
        with _as_user(_OWNER, store, comment_store) as client:
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments",
                json={
                    "body": "Parent comment",
                    "section": "content",
                    "content_piece_index": 3,
                },
            )
            assert r.status_code == 201
            parent_id = r.json()["id"]

            r2 = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments",
                json={
                    "body": "Reply",
                    "section": "content",
                    "content_piece_index": 3,
                    "parent_id": parent_id,
                },
            )
        assert r2.status_code == 201
        assert r2.json()["parent_id"] == parent_id
        assert r2.json()["content_piece_index"] == 3


# ---------------------------------------------------------------------------
# GET .../comments
# ---------------------------------------------------------------------------

class TestListComments:
    """Tests for GET /api/workspaces/{ws}/campaigns/{cid}/comments."""

    def test_owner_can_list_comments(self):
        """200 with empty list when no comments exist."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()
        with _as_user(_OWNER, store, comment_store) as client:
            r = client.get(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments"
            )
        assert r.status_code == 200
        assert r.json() == []

    def test_list_returns_all_comments(self):
        """Returns all comments for the campaign."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "First", CommentSection.STRATEGY)
        )
        asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Second", CommentSection.CONTENT)
        )

        with _as_user(_VIEWER, store, comment_store) as client:
            r = client.get(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments"
            )
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_filter_by_section(self):
        """?section= filters results correctly."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Strategy comment", CommentSection.STRATEGY)
        )
        asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Content comment", CommentSection.CONTENT)
        )

        with _as_user(_OWNER, store, comment_store) as client:
            r = client.get(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments",
                params={"section": "strategy"},
            )
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["section"] == "strategy"

    def test_filter_by_piece_index(self):
        """?piece_index= filters results correctly."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Piece 0", CommentSection.CONTENT, content_piece_index=0)
        )
        asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Piece 1", CommentSection.CONTENT, content_piece_index=1)
        )
        asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Piece 1 again", CommentSection.CONTENT, content_piece_index=1)
        )

        with _as_user(_OWNER, store, comment_store) as client:
            r = client.get(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments",
                params={"piece_index": 1},
            )
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_non_member_gets_404_on_list(self):
        """Non-members get 404 on GET list."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()
        with _as_user(_NON_MEMBER, store, comment_store) as client:
            r = client.get(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments"
            )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET .../comments/count
# ---------------------------------------------------------------------------

class TestCountComments:
    """Tests for GET /api/workspaces/{ws}/campaigns/{cid}/comments/count."""

    def test_count_returns_unresolved(self):
        """Returns { unresolved: N } with the correct count."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        loop = asyncio.get_event_loop()
        c1 = loop.run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "A", CommentSection.GENERAL)
        )
        loop.run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "B", CommentSection.GENERAL)
        )
        loop.run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "C", CommentSection.GENERAL)
        )
        loop.run_until_complete(comment_store.resolve(c1.id))

        with _as_user(_OWNER, store, comment_store) as client:
            r = client.get(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/count"
            )
        assert r.status_code == 200
        assert r.json() == {"unresolved": 2}

    def test_count_zero_when_no_comments(self):
        """Returns 0 when there are no comments."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()
        with _as_user(_OWNER, store, comment_store) as client:
            r = client.get(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/count"
            )
        assert r.status_code == 200
        assert r.json() == {"unresolved": 0}

    def test_non_member_gets_404_on_count(self):
        """Non-members get 404 on count endpoint."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()
        with _as_user(_NON_MEMBER, store, comment_store) as client:
            r = client.get(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/count"
            )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH .../comments/{id}
# ---------------------------------------------------------------------------

class TestUpdateComment:
    """Tests for PATCH /api/workspaces/{ws}/campaigns/{cid}/comments/{comment_id}."""

    def test_author_can_update_own_comment(self):
        """200 when the author updates their own comment."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        comment = asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Original", CommentSection.STRATEGY)
        )

        with _as_user(_OWNER, store, comment_store) as client:
            r = client.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}",
                json={"body": "Updated text"},
            )
        assert r.status_code == 200
        assert r.json()["body"] == "Updated text"

    def test_other_member_cannot_update_comment(self):
        """403 when another member tries to update someone else's comment."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        comment = asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Owner's comment", CommentSection.STRATEGY)
        )

        with _as_user(_EDITOR, store, comment_store) as client:
            r = client.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}",
                json={"body": "Edited by editor"},
            )
        assert r.status_code == 403

    def test_admin_can_update_any_comment(self):
        """200 when an admin updates any comment."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        comment = asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Owner's comment", CommentSection.STRATEGY)
        )

        with _as_user(_ADMIN, store, comment_store) as client:
            r = client.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}",
                json={"body": "Admin edit"},
            )
        assert r.status_code == 200
        assert r.json()["body"] == "Admin edit"

    def test_update_nonexistent_comment_returns_404(self):
        """404 when comment does not exist."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        with _as_user(_OWNER, store, comment_store) as client:
            r = client.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/no-such-id",
                json={"body": "Won't work"},
            )
        assert r.status_code == 404

    def test_update_comment_from_different_campaign_returns_404(self):
        """404 when comment belongs to a different campaign."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        comment = asyncio.get_event_loop().run_until_complete(
            comment_store.create("other-campaign", _OWNER.id, "Other campaign", CommentSection.GENERAL)
        )

        with _as_user(_OWNER, store, comment_store) as client:
            r = client.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}",
                json={"body": "Shouldn't work"},
            )
        assert r.status_code == 404

    def test_empty_body_update_is_rejected(self):
        """422 when body is empty string."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        comment = asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Original", CommentSection.STRATEGY)
        )

        with _as_user(_OWNER, store, comment_store) as client:
            r = client.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}",
                json={"body": ""},
            )
        assert r.status_code == 422

    def test_non_member_gets_404_on_update(self):
        """Non-members get 404 (consistent RBAC pattern)."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        comment = asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Some comment", CommentSection.STRATEGY)
        )

        with _as_user(_NON_MEMBER, store, comment_store) as client:
            r = client.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}",
                json={"body": "Hack"},
            )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE .../comments/{id}
# ---------------------------------------------------------------------------

class TestDeleteComment:
    """Tests for DELETE /api/workspaces/{ws}/campaigns/{cid}/comments/{comment_id}."""

    def test_author_can_delete_own_comment(self):
        """204 when the author deletes their own comment."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        comment = asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "To delete", CommentSection.STRATEGY)
        )

        with _as_user(_OWNER, store, comment_store) as client:
            r = client.delete(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}"
            )
        assert r.status_code == 204

    def test_other_member_cannot_delete_comment(self):
        """403 when another member tries to delete someone else's comment."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        comment = asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Owner's comment", CommentSection.STRATEGY)
        )

        with _as_user(_EDITOR, store, comment_store) as client:
            r = client.delete(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}"
            )
        assert r.status_code == 403

    def test_admin_can_delete_any_comment(self):
        """204 when an admin deletes any comment."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        comment = asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Owner's comment", CommentSection.STRATEGY)
        )

        with _as_user(_ADMIN, store, comment_store) as client:
            r = client.delete(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}"
            )
        assert r.status_code == 204

    def test_delete_nonexistent_comment_returns_404(self):
        """404 when comment does not exist."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        with _as_user(_OWNER, store, comment_store) as client:
            r = client.delete(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/no-such-id"
            )
        assert r.status_code == 404

    def test_delete_comment_from_different_campaign_returns_404(self):
        """404 when comment belongs to a different campaign."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        comment = asyncio.get_event_loop().run_until_complete(
            comment_store.create("other-campaign", _OWNER.id, "Other campaign", CommentSection.GENERAL)
        )

        with _as_user(_OWNER, store, comment_store) as client:
            r = client.delete(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}"
            )
        assert r.status_code == 404

    def test_non_member_gets_404_on_delete(self):
        """Non-members get 404 (consistent RBAC pattern)."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        comment = asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Some comment", CommentSection.STRATEGY)
        )

        with _as_user(_NON_MEMBER, store, comment_store) as client:
            r = client.delete(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}"
            )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH .../comments/{id}/resolve
# ---------------------------------------------------------------------------

class TestResolveComment:
    """Tests for PATCH /api/workspaces/{ws}/campaigns/{cid}/comments/{comment_id}/resolve."""

    def test_owner_can_resolve_comment(self):
        """200 with is_resolved=True after resolving."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        comment = asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Fix this", CommentSection.STRATEGY)
        )

        with _as_user(_OWNER, store, comment_store) as client:
            r = client.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}/resolve"
            )
        assert r.status_code == 200
        assert r.json()["is_resolved"] is True

    def test_editor_can_resolve_comment(self):
        """200 when an editor resolves a comment (requires only WRITE)."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        comment = asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Some issue", CommentSection.CONTENT)
        )

        with _as_user(_EDITOR, store, comment_store) as client:
            r = client.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}/resolve"
            )
        assert r.status_code == 200
        assert r.json()["is_resolved"] is True

    def test_unresolve_comment(self):
        """200 with is_resolved=False when resolved=false query param used."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        loop = asyncio.get_event_loop()
        comment = loop.run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Issue", CommentSection.STRATEGY)
        )
        loop.run_until_complete(comment_store.resolve(comment.id, resolved=True))

        with _as_user(_OWNER, store, comment_store) as client:
            r = client.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}/resolve",
                params={"resolved": "false"},
            )
        assert r.status_code == 200
        assert r.json()["is_resolved"] is False

    def test_viewer_cannot_resolve_comment(self):
        """403 when a viewer tries to resolve a comment."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        comment = asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "An issue", CommentSection.STRATEGY)
        )

        with _as_user(_VIEWER, store, comment_store) as client:
            r = client.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}/resolve"
            )
        assert r.status_code == 403

    def test_resolve_nonexistent_comment_returns_404(self):
        """404 when comment does not exist."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        with _as_user(_OWNER, store, comment_store) as client:
            r = client.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/no-such-id/resolve"
            )
        assert r.status_code == 404

    def test_resolve_comment_from_different_campaign_returns_404(self):
        """404 when comment belongs to a different campaign."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        comment = asyncio.get_event_loop().run_until_complete(
            comment_store.create("other-campaign", _OWNER.id, "Other", CommentSection.GENERAL)
        )

        with _as_user(_OWNER, store, comment_store) as client:
            r = client.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}/resolve"
            )
        assert r.status_code == 404

    def test_non_member_gets_404_on_resolve(self):
        """Non-members get 404 (consistent RBAC pattern)."""
        store, campaign = _make_store_with_campaign()
        comment_store = InMemoryCommentStore()

        comment = asyncio.get_event_loop().run_until_complete(
            comment_store.create(campaign.id, _OWNER.id, "Some comment", CommentSection.STRATEGY)
        )

        with _as_user(_NON_MEMBER, store, comment_store) as client:
            r = client.patch(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/comments/{comment.id}/resolve"
            )
        assert r.status_code == 404
