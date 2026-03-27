"""
Tests for the CommentStore.

Unit tests use InMemoryCommentStore (no database required).
Integration tests target the real PostgreSQL-backed CommentStore and are
skipped automatically when the database is not reachable.
"""

import os
import pytest

from backend.models.campaign import CommentSection
from backend.tests.mock_store import InMemoryCommentStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store():
    return InMemoryCommentStore()


CAMPAIGN_ID = "campaign-1"
AUTHOR_ID = "user-1"


# ---------------------------------------------------------------------------
# Unit tests — async in-memory store
# ---------------------------------------------------------------------------

class TestCommentStoreUnit:

    @pytest.mark.asyncio
    async def test_create_returns_comment(self, store):
        comment = await store.create(
            campaign_id=CAMPAIGN_ID,
            author_id=AUTHOR_ID,
            body="Great strategy!",
            section=CommentSection.STRATEGY,
        )
        assert comment.id is not None
        assert comment.campaign_id == CAMPAIGN_ID
        assert comment.author_id == AUTHOR_ID
        assert comment.body == "Great strategy!"
        assert comment.section == CommentSection.STRATEGY
        assert comment.parent_id is None
        assert comment.is_resolved is False

    @pytest.mark.asyncio
    async def test_create_with_parent(self, store):
        parent = await store.create(
            campaign_id=CAMPAIGN_ID,
            author_id=AUTHOR_ID,
            body="Top-level",
            section=CommentSection.CONTENT,
        )
        reply = await store.create(
            campaign_id=CAMPAIGN_ID,
            author_id="user-2",
            body="Reply",
            section=CommentSection.CONTENT,
            parent_id=parent.id,
        )
        assert reply.parent_id == parent.id

    @pytest.mark.asyncio
    async def test_create_with_content_piece_index(self, store):
        comment = await store.create(
            campaign_id=CAMPAIGN_ID,
            author_id=AUTHOR_ID,
            body="Fix this piece",
            section=CommentSection.CONTENT,
            content_piece_index=3,
        )
        assert comment.content_piece_index == 3

    @pytest.mark.asyncio
    async def test_get_existing(self, store):
        comment = await store.create(
            campaign_id=CAMPAIGN_ID,
            author_id=AUTHOR_ID,
            body="Hello",
            section=CommentSection.GENERAL,
        )
        fetched = await store.get(comment.id)
        assert fetched is not None
        assert fetched.id == comment.id

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, store):
        result = await store.get("does-not-exist")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_campaign_empty(self, store):
        results = await store.list_by_campaign("no-such-campaign")
        assert results == []

    @pytest.mark.asyncio
    async def test_list_by_campaign_returns_all(self, store):
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "A", CommentSection.STRATEGY)
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "B", CommentSection.CONTENT)
        await store.create("other-campaign", AUTHOR_ID, "C", CommentSection.GENERAL)
        results = await store.list_by_campaign(CAMPAIGN_ID)
        assert len(results) == 2
        assert all(c.campaign_id == CAMPAIGN_ID for c in results)

    @pytest.mark.asyncio
    async def test_list_by_campaign_filter_section(self, store):
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "A", CommentSection.STRATEGY)
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "B", CommentSection.CONTENT)
        results = await store.list_by_campaign(CAMPAIGN_ID, section=CommentSection.STRATEGY)
        assert len(results) == 1
        assert results[0].body == "A"

    @pytest.mark.asyncio
    async def test_list_by_campaign_filter_content_piece_index(self, store):
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "piece 0", CommentSection.CONTENT, content_piece_index=0)
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "piece 1", CommentSection.CONTENT, content_piece_index=1)
        results = await store.list_by_campaign(CAMPAIGN_ID, section=CommentSection.CONTENT, content_piece_index=0)
        assert len(results) == 1
        assert results[0].content_piece_index == 0

    @pytest.mark.asyncio
    async def test_update_body(self, store):
        comment = await store.create(CAMPAIGN_ID, AUTHOR_ID, "Original", CommentSection.GENERAL)
        updated = await store.update(comment.id, "Updated body")
        assert updated.body == "Updated body"

    @pytest.mark.asyncio
    async def test_update_nonexistent_raises(self, store):
        with pytest.raises(KeyError):
            await store.update("no-such-id", "body")

    @pytest.mark.asyncio
    async def test_delete_removes_comment(self, store):
        comment = await store.create(CAMPAIGN_ID, AUTHOR_ID, "To delete", CommentSection.GENERAL)
        await store.delete(comment.id)
        assert await store.get(comment.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_is_noop(self, store):
        # Should not raise
        await store.delete("no-such-id")

    @pytest.mark.asyncio
    async def test_delete_parent_re_parents_replies(self, store):
        parent = await store.create(CAMPAIGN_ID, AUTHOR_ID, "Parent", CommentSection.GENERAL)
        reply = await store.create(CAMPAIGN_ID, "user-2", "Reply", CommentSection.GENERAL, parent_id=parent.id)
        await store.delete(parent.id)
        fetched_reply = await store.get(reply.id)
        assert fetched_reply is not None
        assert fetched_reply.parent_id is None

    @pytest.mark.asyncio
    async def test_resolve_sets_flag(self, store):
        comment = await store.create(CAMPAIGN_ID, AUTHOR_ID, "Issue", CommentSection.STRATEGY)
        resolved = await store.resolve(comment.id)
        assert resolved.is_resolved is True

    @pytest.mark.asyncio
    async def test_resolve_can_unresolve(self, store):
        comment = await store.create(CAMPAIGN_ID, AUTHOR_ID, "Issue", CommentSection.STRATEGY)
        await store.resolve(comment.id, resolved=True)
        unresolved = await store.resolve(comment.id, resolved=False)
        assert unresolved.is_resolved is False

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_raises(self, store):
        with pytest.raises(KeyError):
            await store.resolve("no-such-id")

    @pytest.mark.asyncio
    async def test_count_unresolved(self, store):
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "A", CommentSection.GENERAL)
        c2 = await store.create(CAMPAIGN_ID, AUTHOR_ID, "B", CommentSection.GENERAL)
        await store.resolve(c2.id)
        count = await store.count_unresolved(CAMPAIGN_ID)
        assert count == 1

    @pytest.mark.asyncio
    async def test_count_unresolved_zero_when_empty(self, store):
        count = await store.count_unresolved("no-campaign")
        assert count == 0

    @pytest.mark.asyncio
    async def test_count_unresolved_only_for_campaign(self, store):
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "A", CommentSection.GENERAL)
        await store.create("other-campaign", AUTHOR_ID, "B", CommentSection.GENERAL)
        count = await store.count_unresolved(CAMPAIGN_ID)
        assert count == 1


# ---------------------------------------------------------------------------
# Singleton accessor test
# ---------------------------------------------------------------------------

def test_get_comment_store_singleton():
    """get_comment_store() must return the same instance on repeated calls."""
    # Import here so we don't need a live DB at import time
    from backend.infrastructure import comment_store as cs_mod

    # Reset singleton so the test is independent of import order
    cs_mod._comment_store = None

    store_a = cs_mod.get_comment_store()
    store_b = cs_mod.get_comment_store()
    assert store_a is store_b


# ---------------------------------------------------------------------------
# Integration tests — skipped when no DB is reachable
# ---------------------------------------------------------------------------

def _db_available() -> bool:
    """Return True only if a DATABASE_URL is configured and connectable."""
    url = os.getenv("DATABASE_URL", "")
    if not url:
        return False
    try:
        import asyncpg  # noqa: F401
        import asyncio
        conn = asyncio.get_event_loop().run_until_complete(
            asyncpg.connect(url.replace("+asyncpg", ""), timeout=2)
        )
        asyncio.get_event_loop().run_until_complete(conn.close())
        return True
    except Exception:
        return False


_skip_no_db = pytest.mark.skipif(
    not _db_available(), reason="DATABASE_URL not configured or database unreachable"
)


@_skip_no_db
class TestCommentStoreIntegration:
    """Integration tests against the real PostgreSQL-backed CommentStore."""

    @pytest.fixture(autouse=True)
    async def _setup_db(self):
        """Initialise DB tables before each test and clean up after."""
        from backend.infrastructure import database as db_mod
        from sqlalchemy import delete as sa_delete
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from sqlalchemy.pool import NullPool

        await db_mod.engine.dispose()

        test_engine = create_async_engine(
            db_mod.DATABASE_URL, echo=False, future=True, poolclass=NullPool
        )
        test_session_factory = async_sessionmaker(
            test_engine, class_=AsyncSession, expire_on_commit=False
        )

        original_session = db_mod.async_session
        db_mod.async_session = test_session_factory

        async with test_engine.begin() as conn:
            await conn.run_sync(db_mod.Base.metadata.create_all)

        yield

        async with test_session_factory() as session:
            await session.execute(sa_delete(db_mod.CampaignCommentRow))
            await session.commit()

        db_mod.async_session = original_session
        await test_engine.dispose()

    @pytest.mark.asyncio
    async def test_create_and_get(self):
        from backend.infrastructure.comment_store import CommentStore
        store = CommentStore()
        comment = await store.create(CAMPAIGN_ID, AUTHOR_ID, "Hello DB", CommentSection.GENERAL)
        fetched = await store.get(comment.id)
        assert fetched is not None
        assert fetched.body == "Hello DB"

    @pytest.mark.asyncio
    async def test_list_by_campaign_with_filter(self):
        from backend.infrastructure.comment_store import CommentStore
        store = CommentStore()
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "S", CommentSection.STRATEGY)
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "C", CommentSection.CONTENT)
        results = await store.list_by_campaign(CAMPAIGN_ID, section=CommentSection.STRATEGY)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_update(self):
        from backend.infrastructure.comment_store import CommentStore
        store = CommentStore()
        comment = await store.create(CAMPAIGN_ID, AUTHOR_ID, "Original", CommentSection.GENERAL)
        updated = await store.update(comment.id, "Updated")
        assert updated.body == "Updated"

    @pytest.mark.asyncio
    async def test_delete(self):
        from backend.infrastructure.comment_store import CommentStore
        store = CommentStore()
        comment = await store.create(CAMPAIGN_ID, AUTHOR_ID, "To delete", CommentSection.GENERAL)
        await store.delete(comment.id)
        assert await store.get(comment.id) is None

    @pytest.mark.asyncio
    async def test_resolve_and_count_unresolved(self):
        from backend.infrastructure.comment_store import CommentStore
        store = CommentStore()
        c1 = await store.create(CAMPAIGN_ID, AUTHOR_ID, "A", CommentSection.GENERAL)
        await store.create(CAMPAIGN_ID, AUTHOR_ID, "B", CommentSection.GENERAL)
        await store.resolve(c1.id)
        count = await store.count_unresolved(CAMPAIGN_ID)
        assert count == 1
