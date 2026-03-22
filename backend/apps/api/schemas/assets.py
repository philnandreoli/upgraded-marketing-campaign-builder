"""
Pydantic request/response schemas for campaign image asset endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class GenerateAssetRequest(BaseModel):
    content_piece_index: int = Field(description="Index into CampaignContent.pieces")
    prompt_override: Optional[str] = Field(
        default=None,
        description="Custom prompt to use instead of the content piece's image_brief.prompt",
    )


class ImageAssetResponse(BaseModel):
    id: str
    campaign_id: str
    content_piece_index: int
    prompt: str
    image_url: Optional[str]
    storage_path: Optional[str]
    dimensions: str
    format: str
    created_at: datetime


class ImageAssetListResponse(BaseModel):
    items: list[ImageAssetResponse]
