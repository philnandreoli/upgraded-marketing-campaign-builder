"""Persona domain models."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class Persona(BaseModel):
    """Workspace-scoped persona record."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("name must not be empty")
        return name

    @field_validator("description")
    @classmethod
    def _normalize_description(cls, value: str) -> str:
        description = value.strip()
        if not description:
            raise ValueError("description must not be empty")
        return description
