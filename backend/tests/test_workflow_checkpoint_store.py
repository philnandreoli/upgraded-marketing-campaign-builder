"""
Tests for WorkflowCheckpointStore.

Unit tests use an in-memory implementation that mirrors the public
interface without requiring a running PostgreSQL instance.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import pytest

from backend.models.workflow import WorkflowCheckpoint, WorkflowWaitType


# ---------------------------------------------------------------------------
# Lightweight in-memory implementation for unit tests
# ---------------------------------------------------------------------------

class InMemoryWorkflowCheckpointStore:
    """Dict-backed checkpoint store for unit tests — no database required."""

    def __init__(self) -> None:
        self._checkpoints: dict[str, WorkflowCheckpoint] = {}

    async def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        self._checkpoints[checkpoint.campaign_id] = checkpoint

    async def get_checkpoint(self, campaign_id: str) -> Optional[WorkflowCheckpoint]:
        return self._checkpoints.get(campaign_id)

    async def delete_checkpoint(self, campaign_id: str) -> bool:
        if campaign_id in self._checkpoints:
            del self._checkpoints[campaign_id]
            return True
        return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store():
    return InMemoryWorkflowCheckpointStore()


@pytest.fixture
def checkpoint():
    now = datetime.utcnow()
    return WorkflowCheckpoint(
        campaign_id="camp-001",
        current_stage="strategy",
        wait_type=None,
        revision_cycle=0,
        resume_token=None,
        context={"key": "value"},
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Unit tests — in-memory store
# ---------------------------------------------------------------------------

class TestWorkflowCheckpointModel:
    """Validate the Pydantic model itself."""

    def test_defaults(self):
        cp = WorkflowCheckpoint(
            campaign_id="c1",
            current_stage="draft",
        )
        assert cp.wait_type is None
        assert cp.revision_cycle == 0
        assert cp.resume_token is None
        assert cp.context == {}
        assert isinstance(cp.created_at, datetime)
        assert isinstance(cp.updated_at, datetime)

    def test_wait_type_clarification(self):
        cp = WorkflowCheckpoint(
            campaign_id="c1",
            current_stage="clarification",
            wait_type=WorkflowWaitType.CLARIFICATION,
        )
        assert cp.wait_type == WorkflowWaitType.CLARIFICATION

    def test_wait_type_content_approval(self):
        cp = WorkflowCheckpoint(
            campaign_id="c1",
            current_stage="content_approval",
            wait_type=WorkflowWaitType.CONTENT_APPROVAL,
        )
        assert cp.wait_type == WorkflowWaitType.CONTENT_APPROVAL

    def test_wait_type_enum_values(self):
        assert WorkflowWaitType.CLARIFICATION == "clarification"
        assert WorkflowWaitType.CONTENT_APPROVAL == "content_approval"

    def test_context_field(self):
        cp = WorkflowCheckpoint(
            campaign_id="c1",
            current_stage="strategy",
            context={"stage_data": [1, 2, 3], "nested": {"a": "b"}},
        )
        assert cp.context["stage_data"] == [1, 2, 3]
        assert cp.context["nested"]["a"] == "b"

    def test_revision_cycle(self):
        cp = WorkflowCheckpoint(
            campaign_id="c1",
            current_stage="content",
            revision_cycle=3,
        )
        assert cp.revision_cycle == 3

    def test_resume_token(self):
        cp = WorkflowCheckpoint(
            campaign_id="c1",
            current_stage="content",
            resume_token="tok-abc123",
        )
        assert cp.resume_token == "tok-abc123"


class TestWorkflowCheckpointStoreUnit:
    """CRUD tests against the in-memory store."""

    @pytest.mark.asyncio
    async def test_save_and_get(self, store, checkpoint):
        await store.save_checkpoint(checkpoint)
        fetched = await store.get_checkpoint(checkpoint.campaign_id)
        assert fetched is not None
        assert fetched.campaign_id == checkpoint.campaign_id
        assert fetched.current_stage == checkpoint.current_stage

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, store):
        result = await store.get_checkpoint("no-such-campaign")
        assert result is None

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, store, checkpoint):
        await store.save_checkpoint(checkpoint)

        updated = WorkflowCheckpoint(
            campaign_id=checkpoint.campaign_id,
            current_stage="content",
            wait_type=WorkflowWaitType.CONTENT_APPROVAL,
            revision_cycle=2,
            resume_token="tok-xyz",
            context={"updated": True},
            created_at=checkpoint.created_at,
            updated_at=datetime.utcnow(),
        )
        await store.save_checkpoint(updated)

        fetched = await store.get_checkpoint(checkpoint.campaign_id)
        assert fetched is not None
        assert fetched.current_stage == "content"
        assert fetched.wait_type == WorkflowWaitType.CONTENT_APPROVAL
        assert fetched.revision_cycle == 2
        assert fetched.resume_token == "tok-xyz"
        assert fetched.context == {"updated": True}

    @pytest.mark.asyncio
    async def test_delete_existing(self, store, checkpoint):
        await store.save_checkpoint(checkpoint)
        deleted = await store.delete_checkpoint(checkpoint.campaign_id)
        assert deleted is True
        assert await store.get_checkpoint(checkpoint.campaign_id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, store):
        deleted = await store.delete_checkpoint("no-such-campaign")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_save_multiple_campaigns(self, store):
        now = datetime.utcnow()
        cp1 = WorkflowCheckpoint(
            campaign_id="camp-1",
            current_stage="strategy",
            created_at=now,
            updated_at=now,
        )
        cp2 = WorkflowCheckpoint(
            campaign_id="camp-2",
            current_stage="content",
            wait_type=WorkflowWaitType.CONTENT_APPROVAL,
            created_at=now,
            updated_at=now,
        )
        await store.save_checkpoint(cp1)
        await store.save_checkpoint(cp2)

        fetched1 = await store.get_checkpoint("camp-1")
        fetched2 = await store.get_checkpoint("camp-2")
        assert fetched1 is not None
        assert fetched1.current_stage == "strategy"
        assert fetched2 is not None
        assert fetched2.current_stage == "content"
        assert fetched2.wait_type == WorkflowWaitType.CONTENT_APPROVAL

    @pytest.mark.asyncio
    async def test_delete_one_does_not_affect_other(self, store):
        now = datetime.utcnow()
        cp1 = WorkflowCheckpoint(
            campaign_id="camp-1",
            current_stage="strategy",
            created_at=now,
            updated_at=now,
        )
        cp2 = WorkflowCheckpoint(
            campaign_id="camp-2",
            current_stage="content",
            created_at=now,
            updated_at=now,
        )
        await store.save_checkpoint(cp1)
        await store.save_checkpoint(cp2)
        await store.delete_checkpoint("camp-1")

        assert await store.get_checkpoint("camp-1") is None
        assert await store.get_checkpoint("camp-2") is not None

    @pytest.mark.asyncio
    async def test_context_round_trip(self, store):
        """Arbitrary nested context is preserved exactly."""
        now = datetime.utcnow()
        ctx = {"list": [1, 2, 3], "nested": {"a": 1}, "flag": True}
        cp = WorkflowCheckpoint(
            campaign_id="camp-ctx",
            current_stage="analytics_setup",
            context=ctx,
            created_at=now,
            updated_at=now,
        )
        await store.save_checkpoint(cp)
        fetched = await store.get_checkpoint("camp-ctx")
        assert fetched is not None
        assert fetched.context == ctx


# ---------------------------------------------------------------------------
# Integration tests — real PostgreSQL store (skipped when DB unavailable)
# ---------------------------------------------------------------------------

import os  # noqa: E402

_skip_no_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — PostgreSQL integration tests skipped",
)


@_skip_no_db
class TestWorkflowCheckpointStoreIntegration:
    """Integration tests against the real PostgreSQL-backed store."""

    @pytest.fixture(autouse=True)
    async def _setup_db(self):
        from backend.services import database as db_mod
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
            await session.execute(sa_delete(db_mod.WorkflowCheckpointRow))
            await session.execute(sa_delete(db_mod.CampaignRow))
            await session.commit()

        await test_engine.dispose()
        db_mod.async_session = original_session

    @pytest.fixture
    def pg_store(self):
        from backend.services.workflow_checkpoint_store import WorkflowCheckpointStore
        return WorkflowCheckpointStore()

    @pytest.fixture
    async def persisted_campaign(self):
        """Insert a campaign row so FK constraints are satisfied."""
        from backend.services import database as db_mod
        from backend.infrastructure.database import async_session, CampaignRow
        from datetime import datetime

        now = datetime.utcnow()
        row = CampaignRow(
            id="integ-camp-001",
            owner_id=None,
            status="draft",
            data='{"id": "integ-camp-001", "status": "draft"}',
            created_at=now,
            updated_at=now,
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
        return "integ-camp-001"

    @pytest.mark.asyncio
    async def test_save_and_get(self, pg_store, persisted_campaign):
        now = datetime.utcnow()
        cp = WorkflowCheckpoint(
            campaign_id=persisted_campaign,
            current_stage="strategy",
            created_at=now,
            updated_at=now,
        )
        await pg_store.save_checkpoint(cp)
        fetched = await pg_store.get_checkpoint(persisted_campaign)
        assert fetched is not None
        assert fetched.campaign_id == persisted_campaign
        assert fetched.current_stage == "strategy"

    @pytest.mark.asyncio
    async def test_upsert(self, pg_store, persisted_campaign):
        now = datetime.utcnow()
        cp = WorkflowCheckpoint(
            campaign_id=persisted_campaign,
            current_stage="strategy",
            created_at=now,
            updated_at=now,
        )
        await pg_store.save_checkpoint(cp)

        updated = WorkflowCheckpoint(
            campaign_id=persisted_campaign,
            current_stage="content",
            wait_type=WorkflowWaitType.CONTENT_APPROVAL,
            revision_cycle=1,
            created_at=now,
            updated_at=datetime.utcnow(),
        )
        await pg_store.save_checkpoint(updated)

        fetched = await pg_store.get_checkpoint(persisted_campaign)
        assert fetched is not None
        assert fetched.current_stage == "content"
        assert fetched.wait_type == WorkflowWaitType.CONTENT_APPROVAL
        assert fetched.revision_cycle == 1

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, pg_store):
        result = await pg_store.get_checkpoint("no-such-campaign")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, pg_store, persisted_campaign):
        now = datetime.utcnow()
        cp = WorkflowCheckpoint(
            campaign_id=persisted_campaign,
            current_stage="review",
            created_at=now,
            updated_at=now,
        )
        await pg_store.save_checkpoint(cp)
        deleted = await pg_store.delete_checkpoint(persisted_campaign)
        assert deleted is True
        assert await pg_store.get_checkpoint(persisted_campaign) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, pg_store):
        deleted = await pg_store.delete_checkpoint("no-such-campaign")
        assert deleted is False
