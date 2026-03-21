"""
PostgreSQL-backed user settings store.
"""

from __future__ import annotations

from datetime import datetime

from backend.infrastructure.database import UserSettingsRow, async_session
from backend.models.user_settings import UserSettings, UserSettingsPatch


class UserSettingsStore:
    """Repository for per-user settings keyed by user_id."""

    async def get(self, user_id: str) -> UserSettings:
        """Return settings for *user_id*, creating sensible defaults when missing."""
        async with async_session() as session:
            row = await session.get(UserSettingsRow, user_id)
            if row is None:
                now = datetime.utcnow()
                row = UserSettingsRow(
                    user_id=user_id,
                    ui_theme="system",
                    locale="en-US",
                    timezone="UTC",
                    default_workspace_id=None,
                    notification_prefs={},
                    dashboard_prefs={},
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                await session.commit()
            return self._to_model(row)

    async def patch(self, user_id: str, patch: UserSettingsPatch) -> UserSettings:
        """Apply partial updates to the user settings row, creating defaults if absent."""
        async with async_session() as session:
            row = await session.get(UserSettingsRow, user_id)
            if row is None:
                now = datetime.utcnow()
                row = UserSettingsRow(
                    user_id=user_id,
                    ui_theme="system",
                    locale="en-US",
                    timezone="UTC",
                    default_workspace_id=None,
                    notification_prefs={},
                    dashboard_prefs={},
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                await session.flush()

            changes = patch.model_dump(exclude_unset=True)
            for key, value in changes.items():
                if key == "ui_theme" and value is not None:
                    setattr(row, key, value.value)
                else:
                    setattr(row, key, value)
            row.updated_at = datetime.utcnow()
            await session.commit()
            return self._to_model(row)

    @staticmethod
    def _to_model(row: UserSettingsRow) -> UserSettings:
        return UserSettings(
            user_id=row.user_id,
            ui_theme=row.ui_theme,
            locale=row.locale,
            timezone=row.timezone,
            default_workspace_id=row.default_workspace_id,
            notification_prefs=row.notification_prefs or {},
            dashboard_prefs=row.dashboard_prefs or {},
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


_user_settings_store: UserSettingsStore | None = None


def get_user_settings_store() -> UserSettingsStore:
    global _user_settings_store
    if _user_settings_store is None:
        _user_settings_store = UserSettingsStore()
    return _user_settings_store
