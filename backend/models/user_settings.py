"""
User settings models for durable, per-user preferences.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class UITheme(str, Enum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class UserSettings(BaseModel):
    user_id: str
    ui_theme: UITheme = Field(default=UITheme.SYSTEM)
    locale: str = Field(default="en-US")
    timezone: str = Field(default="UTC")
    default_workspace_id: str | None = None
    notification_prefs: dict[str, Any] = Field(default_factory=dict)
    dashboard_prefs: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UserSettingsPatch(BaseModel):
    ui_theme: UITheme | None = None
    locale: str | None = None
    timezone: str | None = None
    default_workspace_id: str | None = None
    notification_prefs: dict[str, Any] | None = None
    dashboard_prefs: dict[str, Any] | None = None
