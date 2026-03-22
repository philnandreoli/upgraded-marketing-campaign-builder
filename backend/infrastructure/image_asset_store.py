"""PostgreSQL-backed image asset store."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import delete as sa_delete, select

from backend.infrastructure.database import ImageAssetRow, async_session
from backend.models.campaign import ImageAsset


class ImageAssetStore:
    """Repository for ``ImageAssetRow`` records backed by PostgreSQL."""

    async def create(self, asset: ImageAsset) -> ImageAsset:
        """Insert an image asset row and return the persisted model."""
        row = ImageAssetRow(
            id=asset.id,
            campaign_id=asset.campaign_id,
            content_piece_index=asset.content_piece_index,
            prompt=asset.prompt,
            image_url=asset.image_url,
            storage_path=asset.storage_path,
            dimensions=asset.dimensions,
            format=asset.format,
            created_at=asset.created_at,
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
        return self._to_model(row)

    async def list_by_campaign(self, campaign_id: str) -> list[ImageAsset]:
        """Return all assets for a campaign ordered newest-first."""
        async with async_session() as session:
            result = await session.execute(
                select(ImageAssetRow)
                .where(ImageAssetRow.campaign_id == campaign_id)
                .order_by(ImageAssetRow.created_at.desc())
            )
            rows = result.scalars().all()
        return [self._to_model(row) for row in rows]

    async def get(self, asset_id: str) -> Optional[ImageAsset]:
        """Return one image asset by ID, or ``None`` if not found."""
        async with async_session() as session:
            row = await session.get(ImageAssetRow, asset_id)
            if row is None:
                return None
        return self._to_model(row)

    async def delete(self, asset_id: str) -> None:
        """Delete an image asset row by ID."""
        async with async_session() as session:
            await session.execute(sa_delete(ImageAssetRow).where(ImageAssetRow.id == asset_id))
            await session.commit()

    @staticmethod
    def _to_model(row: ImageAssetRow) -> ImageAsset:
        return ImageAsset(
            id=row.id,
            campaign_id=row.campaign_id,
            content_piece_index=row.content_piece_index,
            prompt=row.prompt,
            image_url=row.image_url,
            storage_path=row.storage_path,
            dimensions=row.dimensions,
            format=row.format,
            created_at=row.created_at,
        )


_image_asset_store: ImageAssetStore | None = None


def get_image_asset_store() -> ImageAssetStore:
    global _image_asset_store
    if _image_asset_store is None:
        _image_asset_store = ImageAssetStore()
    return _image_asset_store
