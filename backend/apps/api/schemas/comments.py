"""
Pydantic request/response schemas for campaign comment API endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.models.campaign import CommentSection


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class CreateCommentRequest(BaseModel):
    """Request body for creating a new campaign comment."""

    body: str = Field(min_length=1, description="Comment text content.")
    section: CommentSection = Field(description="Campaign section this comment targets.")
    content_piece_index: Optional[int] = Field(
        default=None,
        description="Index into CampaignContent.pieces. Only relevant when section=content.",
    )
    parent_id: Optional[str] = Field(
        default=None,
        description="ID of the parent comment. None indicates a top-level comment.",
    )


class UpdateCommentRequest(BaseModel):
    """Request body for updating an existing campaign comment."""

    body: str = Field(min_length=1, description="Updated comment text content.")


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class CommentResponse(BaseModel):
    """Full comment representation returned by the API."""

    id: str
    campaign_id: str
    parent_id: Optional[str]
    section: CommentSection
    content_piece_index: Optional[int]
    body: str
    author_id: str
    is_resolved: bool
    created_at: datetime
    updated_at: datetime
