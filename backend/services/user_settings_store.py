"""Backward-compatible shim for user settings store imports."""

from backend.infrastructure.user_settings_store import (
    UserSettingsStore,
    get_user_settings_store,
)

__all__ = ["UserSettingsStore", "get_user_settings_store"]
