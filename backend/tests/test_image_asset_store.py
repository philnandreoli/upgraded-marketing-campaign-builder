from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.infrastructure.database import CampaignRow, ImageAssetRow
from backend.infrastructure.image_asset_store import ImageAssetStore, get_image_asset_store
from backend.models.campaign import ImageAsset


@pytest.fixture
async def store_with_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: CampaignRow.metadata.create_all(
                sync_conn,
                tables=[CampaignRow.__table__, ImageAssetRow.__table__],
            )
        )

    async with session_factory() as session:
        now = datetime.utcnow()
        session.add(
            CampaignRow(
                id="campaign-1",
                owner_id=None,
                status="draft",
                data='{"id": "campaign-1", "status": "draft"}',
                created_at=now,
                updated_at=now,
                workspace_id=None,
                version=1,
            )
        )
        await session.commit()

    with patch("backend.infrastructure.image_asset_store.async_session", session_factory):
        yield ImageAssetStore()

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_persists_and_returns_asset(store_with_db):
    asset = ImageAsset(
        id="asset-1",
        campaign_id="campaign-1",
        content_piece_index=0,
        prompt="Create a hero image",
        image_url="https://example.com/a.png",
        storage_path="campaign-1/asset-1.png",
    )

    created = await store_with_db.create(asset)
    fetched = await store_with_db.get("asset-1")

    assert created.id == "asset-1"
    assert fetched is not None
    assert fetched.id == "asset-1"
    assert fetched.prompt == "Create a hero image"


@pytest.mark.asyncio
async def test_list_by_campaign_orders_created_at_desc(store_with_db):
    now = datetime.utcnow()
    older = ImageAsset(
        id="asset-old",
        campaign_id="campaign-1",
        content_piece_index=0,
        prompt="old",
        created_at=now - timedelta(minutes=5),
    )
    newer = ImageAsset(
        id="asset-new",
        campaign_id="campaign-1",
        content_piece_index=1,
        prompt="new",
        created_at=now,
    )

    await store_with_db.create(older)
    await store_with_db.create(newer)

    assets = await store_with_db.list_by_campaign("campaign-1")

    assert [asset.id for asset in assets] == ["asset-new", "asset-old"]


@pytest.mark.asyncio
async def test_get_returns_none_when_missing(store_with_db):
    assert await store_with_db.get("missing") is None


@pytest.mark.asyncio
async def test_delete_removes_asset(store_with_db):
    asset = ImageAsset(
        id="asset-delete",
        campaign_id="campaign-1",
        content_piece_index=0,
        prompt="delete me",
    )
    await store_with_db.create(asset)

    await store_with_db.delete("asset-delete")

    assert await store_with_db.get("asset-delete") is None


def test_get_image_asset_store_singleton():
    with patch("backend.infrastructure.image_asset_store._image_asset_store", None):
        first = get_image_asset_store()
        second = get_image_asset_store()

    assert first is second
