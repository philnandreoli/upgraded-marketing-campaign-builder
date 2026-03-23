"""
Campaign image asset routes.

Endpoints:
  POST /api/workspaces/{workspace_id}/campaigns/{campaign_id}/assets/generate
      — Trigger image generation for a content piece
  GET  /api/workspaces/{workspace_id}/campaigns/{campaign_id}/assets
      — List generated image assets for a campaign
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.config import get_settings
from backend.models.campaign import Campaign, ImageAsset
from backend.infrastructure.image_asset_store import get_image_asset_store
from backend.infrastructure.image_generation_service import get_image_generation_service
from backend.infrastructure.image_storage_service import get_image_storage_service

from backend.apps.api.dependencies import get_campaign_for_read, get_campaign_for_write
from backend.apps.api.schemas.assets import (
    GenerateAssetRequest,
    ImageAssetListResponse,
    ImageAssetResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["campaign-assets"])


def _asset_to_response(asset: ImageAsset) -> ImageAssetResponse:
    return ImageAssetResponse(
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


@router.post(
    "/campaigns/{campaign_id}/assets/generate",
    response_model=ImageAssetResponse,
    status_code=201,
)
async def generate_asset(
    body: GenerateAssetRequest,
    campaign: Campaign = Depends(get_campaign_for_write),
) -> ImageAssetResponse:
    """Generate an image asset for a content piece.

    Returns 501 when the platform-level ``IMAGE_GENERATION_ENABLED`` flag is
    false.  Returns 400 when the campaign brief did not opt in to image
    generation (``generate_images=False``) or when ``content_piece_index`` is
    out of range.
    """
    settings = get_settings()
    if not settings.image_generation.enabled:
        raise HTTPException(
            status_code=501,
            detail="Image generation is not enabled on this platform.",
        )

    if not campaign.brief.generate_images:
        raise HTTPException(
            status_code=400,
            detail="Image generation was not enabled for this campaign.",
        )

    if campaign.content is None or not campaign.content.pieces:
        raise HTTPException(
            status_code=400,
            detail="Campaign has no content pieces.",
        )

    idx = body.content_piece_index
    if idx < 0 or idx >= len(campaign.content.pieces):
        raise HTTPException(
            status_code=400,
            detail=f"content_piece_index {idx} is out of range (0–{len(campaign.content.pieces) - 1}).",
        )

    piece = campaign.content.pieces[idx]

    if body.prompt_override:
        prompt = body.prompt_override
    else:
        if piece.image_brief is None or not piece.image_brief.prompt:
            raise HTTPException(
                status_code=400,
                detail=f"Content piece at index {idx} has no image brief prompt. Provide a prompt_override.",
            )
        prompt = piece.image_brief.prompt

    dimensions = piece.image_brief.suggested_dimensions if piece.image_brief else "1024x1024"

    asset = ImageAsset(
        campaign_id=campaign.id,
        content_piece_index=idx,
        prompt=prompt,
        dimensions=dimensions,
    )

    gen_service = get_image_generation_service()
    try:
        image_bytes = await gen_service.generate(prompt, dimensions)
    except Exception:
        logger.exception("Image generation failed for campaign %s, piece %d", campaign.id, idx)
        raise HTTPException(
            status_code=502,
            detail="Image generation service returned an error. Check server logs for details.",
        )

    storage_service = get_image_storage_service()
    try:
        storage_path, image_url = await storage_service.upload(
            campaign_id=campaign.id,
            asset_id=asset.id,
            image_bytes=image_bytes,
            fmt=asset.format,
        )
    except Exception:
        logger.exception("Image storage upload failed for campaign %s, asset %s", campaign.id, asset.id)
        raise HTTPException(
            status_code=502,
            detail="Failed to upload generated image to storage. Check server logs for details.",
        )

    asset.storage_path = storage_path
    asset.image_url = image_url

    store = get_image_asset_store()
    created = await store.create(asset)

    logger.info(
        "Image asset %s created for campaign %s, piece %d",
        created.id,
        campaign.id,
        idx,
    )
    return _asset_to_response(created)


@router.get(
    "/campaigns/{campaign_id}/assets",
    response_model=ImageAssetListResponse,
)
async def list_assets(
    campaign: Campaign = Depends(get_campaign_for_read),
    content_piece_index: Optional[int] = Query(
        default=None,
        description="Filter assets by content piece index",
    ),
) -> ImageAssetListResponse:
    """List image assets for a campaign, optionally filtered by content piece index."""
    store = get_image_asset_store()
    assets = await store.list_by_campaign(campaign.id)

    if content_piece_index is not None:
        assets = [a for a in assets if a.content_piece_index == content_piece_index]

    # Refresh SAS URLs so they are always valid when returned to the client.
    storage_service = get_image_storage_service()
    for asset in assets:
        if asset.storage_path:
            try:
                asset.image_url = await storage_service.generate_sas_url(asset.storage_path)
            except Exception:
                logger.warning(
                    "Failed to refresh SAS URL for asset %s — returning stale URL",
                    asset.id,
                    exc_info=True,
                )

    return ImageAssetListResponse(items=[_asset_to_response(a) for a in assets])
