"""
Tests for the CommentStore.

Unit tests use the InMemoryCommentStore (no database required).
"""

import pytest
from backend.models.campaign import CommentSection
from backend.tests.mock_store import InMemoryCommentStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store():
    return InMemoryCommentStore()


CAMPAIGN_ID = "campaign-001"
AUTHOR_ID = "user-001"


# ---------------------------------------------------------------------------
# Unit tests — async in-memory store
# ---------------------------------------------------------------------------

class TestCommentStoreUnit:
    @pytest.mark.asyncio
    async def test_create_returns_comment(self, store):
        comment = await store.create(
            campaign_id=CAMPAIGN_ID,
            author_id=AUTHOR_ID,
            body="Hello world",
            section=CommentSection.STRATEGY,
        )
        assert comment.id is not None
        assert comment.campaign_id == CAMPAIGN_ID
        assert comment.author_id == AUTHOR_ID
        assert comment.body == "Hello world"
        assert comment.section == CommentSection.STRATEGY
        assert comment.is_resolved is False
        assert comment.parent_id is None

    @pytest.mark.asyncio
    async def test_create_with_parent_and_index(self, store):
        parent = await store.create(
            campaign_id=CAMPAIGN_ID,
            author_id=AUTHOR_ID,
            body="Parent",
            section=CommentSection.CONTENT,
            content_piece_index=2,
        )
        child = await store.create(
            campaign_id=CAMPAIGN_ID,
            author_id=AUTHOR_ID,
            body="Reply",
            section=CommentSection.CONTENT,
            parent_id=parent.id,
            content_piece_index=2,
        )
        assert child.parent_id == parent.id
        assert child.content_piece_index == 2

    @pytest.mark.asyncio
    async def test_get_existing(self, store):
        created = await store.create(
            campaign_id=CAMPAIGN_ID,
            author_id=AUTHOR_ID,
            body="Body",
            section=CommentSection.GENERAL,
        )
        fetched = await store.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, store):
        assert await store.get("no-such-id") is None

    @pytest.mark.asyncio
    async def test_list_by_campaign_all(self, store):
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "A", CommentSection.STRATEGY)
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "B", CommentSection.CONTENT)
        await store.create("other-campaign", AUTHOR_ID, "C", CommentSection.GENERAL)

        results = await store.list_by_campaign(CAMPAIGN_ID)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_list_by_campaign_filter_section(self, store):
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "A", CommentSection.STRATEGY)
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "B", CommentSection.CONTENT)

        results = await store.list_by_campaign(CAMPAIGN_ID, section=CommentSection.STRATEGY)
        assert len(results) == 1
        assert results[0].section == CommentSection.STRATEGY

    @pytest.mark.asyncio
    async def test_list_by_campaign_filter_content_piece_index(self, store):
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "A", CommentSection.CONTENT, content_piece_index=0)
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "B", CommentSection.CONTENT, content_piece_index=1)
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "C", CommentSection.CONTENT, content_piece_index=1)

        results = await store.list_by_campaign(CAMPAIGN_ID, content_piece_index=1)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_list_by_campaign_combined_filters(self, store):
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "A", CommentSection.CONTENT, content_piece_index=0)
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "B", CommentSection.CONTENT, content_piece_index=1)
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "C", CommentSection.STRATEGY)

        results = await store.list_by_campaign(
            CAMPAIGN_ID, section=CommentSection.CONTENT, content_piece_index=0
        )
        assert len(results) == 1
        assert results[0].body == "A"

    @pytest.mark.asyncio
    async def test_create_with_nonexistent_parent_id(self, store):
        """Store does not validate parent_id — it stores as-is."""
        comment = await store.create(
            campaign_id=CAMPAIGN_ID,
            author_id=AUTHOR_ID,
            body="Orphaned reply",
            section=CommentSection.GENERAL,
            parent_id="nonexistent-parent",
        )
        assert comment.parent_id == "nonexistent-parent"
        fetched = await store.get(comment.id)
        assert fetched is not None
        assert fetched.parent_id == "nonexistent-parent"

    @pytest.mark.asyncio
    async def test_update_body(self, store):
        comment = await store.create(CAMPAIGN_ID, AUTHOR_ID, "Original", CommentSection.GENERAL)
        updated = await store.update(comment.id, "Updated text")
        assert updated.body == "Updated text"
        assert updated.id == comment.id

    @pytest.mark.asyncio
    async def test_update_nonexistent_raises(self, store):
        with pytest.raises(ValueError, match="not found"):
            await store.update("no-such-id", "new body")

    @pytest.mark.asyncio
    async def test_delete_removes_comment(self, store):
        comment = await store.create(CAMPAIGN_ID, AUTHOR_ID, "To delete", CommentSection.GENERAL)
        await store.delete(comment.id)
        assert await store.get(comment.id) is None

    @pytest.mark.asyncio
    async def test_delete_cascades_to_replies(self, store):
        parent = await store.create(CAMPAIGN_ID, AUTHOR_ID, "Parent", CommentSection.STRATEGY)
        reply = await store.create(
            CAMPAIGN_ID, AUTHOR_ID, "Reply", CommentSection.STRATEGY, parent_id=parent.id
        )
        await store.delete(parent.id)
        assert await store.get(parent.id) is None
        assert await store.get(reply.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_is_silent(self, store):
        # Should not raise even if comment doesn't exist.
        await store.delete("no-such-id")

    @pytest.mark.asyncio
    async def test_resolve_marks_resolved(self, store):
        comment = await store.create(CAMPAIGN_ID, AUTHOR_ID, "Fix this", CommentSection.ANALYTICS)
        resolved = await store.resolve(comment.id)
        assert resolved.is_resolved is True

    @pytest.mark.asyncio
    async def test_resolve_false_unmarks(self, store):
        comment = await store.create(CAMPAIGN_ID, AUTHOR_ID, "Fix this", CommentSection.ANALYTICS)
        await store.resolve(comment.id, resolved=True)
        unresolved = await store.resolve(comment.id, resolved=False)
        assert unresolved.is_resolved is False

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_raises(self, store):
        with pytest.raises(ValueError, match="not found"):
            await store.resolve("no-such-id")

    @pytest.mark.asyncio
    async def test_count_unresolved(self, store):
        c1 = await store.create(CAMPAIGN_ID, AUTHOR_ID, "A", CommentSection.GENERAL)
        c2 = await store.create(CAMPAIGN_ID, AUTHOR_ID, "B", CommentSection.GENERAL)
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "C", CommentSection.GENERAL)

        await store.resolve(c1.id)
        await store.resolve(c2.id)

        count = await store.count_unresolved(CAMPAIGN_ID)
        assert count == 1

    @pytest.mark.asyncio
    async def test_count_unresolved_excludes_other_campaigns(self, store):
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "A", CommentSection.GENERAL)
        await store.create("other-campaign", AUTHOR_ID, "B", CommentSection.GENERAL)

        count = await store.count_unresolved(CAMPAIGN_ID)
        assert count == 1

    @pytest.mark.asyncio
    async def test_count_unresolved_empty(self, store):
        count = await store.count_unresolved(CAMPAIGN_ID)
        assert count == 0
