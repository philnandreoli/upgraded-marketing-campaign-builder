from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.infrastructure.database import PersonaRow, UserRow, WorkspaceRow
from backend.infrastructure.persona_store import PersonaStore, get_persona_store


@pytest.fixture
async def store_with_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: PersonaRow.metadata.create_all(
                sync_conn,
                tables=[UserRow.__table__, WorkspaceRow.__table__, PersonaRow.__table__],
            )
        )

    async with session_factory() as session:
        now = datetime.utcnow()
        session.add(
            UserRow(
                id="user-1",
                email="u1@example.com",
                display_name="User One",
                role="campaign_builder",
                created_at=now,
                updated_at=now,
                is_active=True,
            )
        )
        session.add(
            WorkspaceRow(
                id="ws-1",
                name="Workspace",
                description=None,
                owner_id="user-1",
                is_personal=False,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    with patch("backend.infrastructure.persona_store.async_session", session_factory):
        yield PersonaStore()

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_and_get_persona(store_with_db):
    created = await store_with_db.create(
        workspace_id="ws-1",
        name="IT Manager Maria",
        description="Leads tooling decisions for operations team",
        created_by="user-1",
    )
    fetched = await store_with_db.get(created.id)
    assert fetched is not None
    assert fetched.name == "IT Manager Maria"
    assert fetched.workspace_id == "ws-1"


@pytest.mark.asyncio
async def test_list_by_workspace(store_with_db):
    await store_with_db.create(
        workspace_id="ws-1",
        name="Persona A",
        description="Description A",
        created_by="user-1",
    )
    await store_with_db.create(
        workspace_id="ws-1",
        name="Persona B",
        description="Description B",
        created_by="user-1",
    )
    items, total = await store_with_db.list_by_workspace("ws-1")
    assert total == 2
    assert len(items) == 2


@pytest.mark.asyncio
async def test_update_persona(store_with_db):
    created = await store_with_db.create(
        workspace_id="ws-1",
        name="Original Name",
        description="Original Description",
        created_by="user-1",
    )
    updated = await store_with_db.update(
        created.id,
        name="Updated Name",
        description="Updated Description",
    )
    assert updated.name == "Updated Name"
    assert updated.description == "Updated Description"


@pytest.mark.asyncio
async def test_delete_persona(store_with_db):
    created = await store_with_db.create(
        workspace_id="ws-1",
        name="Delete Me",
        description="To be removed",
        created_by="user-1",
    )
    deleted = await store_with_db.delete(created.id)
    assert deleted is True
    assert await store_with_db.get(created.id) is None


@pytest.mark.asyncio
async def test_list_for_campaign_preserves_order_and_scope(store_with_db):
    p1 = await store_with_db.create(
        workspace_id="ws-1",
        name="Persona One",
        description="One",
        created_by="user-1",
    )
    p2 = await store_with_db.create(
        workspace_id="ws-1",
        name="Persona Two",
        description="Two",
        created_by="user-1",
    )

    ordered = await store_with_db.list_for_campaign(
        workspace_id="ws-1",
        persona_ids=[p2.id, p1.id],
    )
    assert [persona.id for persona in ordered] == [p2.id, p1.id]


def test_get_persona_store_singleton():
    with patch("backend.infrastructure.persona_store._persona_store", None):
        first = get_persona_store()
        second = get_persona_store()
    assert first is second
