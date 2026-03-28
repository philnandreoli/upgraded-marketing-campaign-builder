"""Pydantic schemas for persona API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.apps.api.schemas.common import PaginationMeta


class PersonaResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class PersonaListResponse(BaseModel):
    items: list[PersonaResponse]
    pagination: PaginationMeta


class CreatePersonaRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)


class UpdatePersonaRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, min_length=1, max_length=4000)


class ParsePersonaRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)


class ParsePersonaResponse(BaseModel):
    name: str
    demographics: str
    psychographics: str
    pain_points: str
    behaviors: str
    channels: str
