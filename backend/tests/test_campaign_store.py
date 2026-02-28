"""
Tests for the CampaignStore.

Unit tests use the InMemoryCampaignStore (no database required).
Integration tests target the real PostgreSQL-backed CampaignStore and are
skipped automatically when the database is not reachable.
"""

import os
import pytest
from backend.models.campaign import CampaignBrief, CampaignStatus
from backend.tests.mock_store import InMemoryCampaignStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store():
    return InMemoryCampaignStore()


@pytest.fixture
def brief():
    return CampaignBrief(
        product_or_service="CloudSync",
        goal="Increase signups",
        budget=10000,
    )


# ---------------------------------------------------------------------------
# Unit tests — async in-memory store
# ---------------------------------------------------------------------------

class TestCampaignStoreUnit:
    @pytest.mark.asyncio
    async def test_create(self, store, brief):
        c = await store.create(brief)
        assert c.id is not None
        assert c.status == CampaignStatus.DRAFT
        assert c.brief.product_or_service == "CloudSync"

    @pytest.mark.asyncio
    async def test_get_existing(self, store, brief):
        c = await store.create(brief)
        fetched = await store.get(c.id)
        assert fetched is not None
        assert fetched.id == c.id

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, store):
        assert await store.get("not-a-real-id") is None

    @pytest.mark.asyncio
    async def test_list_empty(self, store):
        assert await store.list_all() == []

    @pytest.mark.asyncio
    async def test_list_multiple(self, store, brief):
        await store.create(brief)
        await store.create(brief)
        assert len(await store.list_all()) == 2

    @pytest.mark.asyncio
    async def test_update(self, store, brief):
        c = await store.create(brief)
        c.advance_status(CampaignStatus.STRATEGY)
        await store.update(c)
        fetched = await store.get(c.id)
        assert fetched.status == CampaignStatus.STRATEGY

    @pytest.mark.asyncio
    async def test_delete_existing(self, store, brief):
        c = await store.create(brief)
        assert await store.delete(c.id) is True
        assert await store.get(c.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, store):
        assert await store.delete("not-a-real-id") is False

    @pytest.mark.asyncio
    async def test_delete_removes_from_list(self, store, brief):
        c = await store.create(brief)
        await store.delete(c.id)
        assert len(await store.list_all()) == 0


# ---------------------------------------------------------------------------
# Integration tests — real PostgreSQL store (skipped when DB unavailable)
# ---------------------------------------------------------------------------

def _db_available() -> bool:
    """Check whether the PostgreSQL database is reachable."""
    try:
        import asyncio
        from backend.services.database import engine

        async def _ping():
            async with engine.connect() as conn:
                await conn.execute(engine.dialect.statement_compiler(engine.dialect, None).__class__.__new__(engine.dialect.statement_compiler).__class__.__mro__[0].__call__)  # noqa: E501
        # Simpler check: try importing asyncpg and connecting
        import asyncpg  # noqa: F401
        return "DATABASE_URL" in os.environ
    except Exception:
        return False


_skip_no_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — PostgreSQL integration tests skipped",
)


@_skip_no_db
class TestCampaignStoreIntegration:
    """Integration tests against the real PostgreSQL-backed CampaignStore."""

    @pytest.fixture(autouse=True)
    async def _setup_db(self):
        """Initialise DB tables before each test and clean up after."""
        from backend.services import database as db_mod
        from sqlalchemy import delete as sa_delete
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from sqlalchemy.pool import NullPool

        # Dispose the module-level engine to clear any tainted connections
        # left over from other test modules (e.g. test_api_routes imports)
        await db_mod.engine.dispose()

        # Create a dedicated engine with NullPool to avoid connection state issues
        test_engine = create_async_engine(db_mod.DATABASE_URL, echo=False, future=True, poolclass=NullPool)
        test_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

        # Patch the module-level session factory so the store uses our test engine
        original_session = db_mod.async_session
        db_mod.async_session = test_session_factory

        # Create tables
        async with test_engine.begin() as conn:
            await conn.run_sync(db_mod.Base.metadata.create_all)

        yield

        # Cleanup: delete all rows
        async with test_session_factory() as session:
            await session.execute(sa_delete(db_mod.CampaignRow))
            await session.commit()

        await test_engine.dispose()
        db_mod.async_session = original_session

    @pytest.fixture
    def pg_store(self):
        from backend.services.campaign_store import CampaignStore
        return CampaignStore()

    @pytest.mark.asyncio
    async def test_create_and_get(self, pg_store, brief):
        c = await pg_store.create(brief)
        assert c.id is not None
        fetched = await pg_store.get(c.id)
        assert fetched is not None
        assert fetched.brief.product_or_service == "CloudSync"

    @pytest.mark.asyncio
    async def test_list_all(self, pg_store, brief):
        await pg_store.create(brief)
        await pg_store.create(brief)
        items = await pg_store.list_all()
        assert len(items) >= 2

    @pytest.mark.asyncio
    async def test_update_persists(self, pg_store, brief):
        c = await pg_store.create(brief)
        c.advance_status(CampaignStatus.STRATEGY)
        await pg_store.update(c)
        fetched = await pg_store.get(c.id)
        assert fetched.status == CampaignStatus.STRATEGY

    @pytest.mark.asyncio
    async def test_delete(self, pg_store, brief):
        c = await pg_store.create(brief)
        assert await pg_store.delete(c.id) is True
        assert await pg_store.get(c.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, pg_store):
        assert await pg_store.delete("no-such-id") is False
