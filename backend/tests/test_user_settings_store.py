"""
Tests for user settings persistence model, store behavior, and migration script.
"""

from __future__ import annotations

import importlib
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from backend.models.user import UserRole, roles_to_db
from backend.models.user_settings import UITheme, UserSettings, UserSettingsPatch


class TestUserSettingsModel:
    def test_defaults(self):
        settings = UserSettings(user_id="user-1")
        assert settings.ui_theme == UITheme.SYSTEM
        assert settings.locale == "en-US"
        assert settings.timezone == "UTC"
        assert settings.default_workspace_id is None
        assert settings.notification_prefs == {}
        assert settings.dashboard_prefs == {}


class TestUserSettingsMigration:
    def test_upgrade_creates_table_when_absent(self):
        migration = importlib.import_module("backend.migrations.versions.0014_add_user_settings_table")
        inspector = MagicMock()
        inspector.get_table_names.return_value = ["users", "workspaces"]
        with patch.object(migration, "inspect", return_value=inspector), patch.object(
            migration, "op"
        ) as mock_op:
            mock_op.get_bind.return_value = object()
            migration.upgrade()

        mock_op.create_table.assert_called_once()
        assert mock_op.create_table.call_args.args[0] == "user_settings"

    def test_upgrade_noop_when_table_exists(self):
        migration = importlib.import_module("backend.migrations.versions.0014_add_user_settings_table")
        inspector = MagicMock()
        inspector.get_table_names.return_value = ["users", "workspaces", "user_settings"]
        with patch.object(migration, "inspect", return_value=inspector), patch.object(
            migration, "op"
        ) as mock_op:
            mock_op.get_bind.return_value = object()
            migration.upgrade()

        mock_op.create_table.assert_not_called()

    def test_downgrade_drops_table_when_present(self):
        migration = importlib.import_module("backend.migrations.versions.0014_add_user_settings_table")
        inspector = MagicMock()
        inspector.get_table_names.return_value = ["user_settings"]
        with patch.object(migration, "inspect", return_value=inspector), patch.object(
            migration, "op"
        ) as mock_op:
            mock_op.get_bind.return_value = object()
            migration.downgrade()

        mock_op.drop_table.assert_called_once_with("user_settings")


_skip_no_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — PostgreSQL integration tests skipped",
)


@_skip_no_db
class TestUserSettingsStoreIntegration:
    @pytest.fixture(autouse=True)
    async def _setup_db(self):
        from sqlalchemy import delete as sa_delete
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from backend.services import database as db_mod

        await db_mod.engine.dispose()
        test_engine = create_async_engine(db_mod.DATABASE_URL, echo=False, future=True, poolclass=NullPool)
        test_session_factory = async_sessionmaker(
            test_engine, class_=AsyncSession, expire_on_commit=False
        )

        original_session = db_mod.async_session
        db_mod.async_session = test_session_factory

        async with test_engine.begin() as conn:
            await conn.run_sync(db_mod.Base.metadata.create_all)

        yield

        async with test_session_factory() as session:
            await session.execute(sa_delete(db_mod.UserSettingsRow))
            await session.execute(sa_delete(db_mod.WorkspaceMemberRow))
            await session.execute(sa_delete(db_mod.WorkspaceRow))
            await session.execute(sa_delete(db_mod.UserRow))
            await session.commit()

        await test_engine.dispose()
        db_mod.async_session = original_session

    @pytest.fixture
    async def persisted_user(self):
        from backend.infrastructure.database import UserRow, async_session

        now = datetime.utcnow()
        row = UserRow(
            id="settings-user-1",
            email="settings@example.com",
            display_name="Settings User",
            role=roles_to_db([UserRole.VIEWER]),
            created_at=now,
            updated_at=now,
            is_active=True,
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
        return row.id

    @pytest.fixture
    def store(self):
        from backend.infrastructure.user_settings_store import UserSettingsStore

        return UserSettingsStore()

    @pytest.mark.asyncio
    async def test_get_creates_defaults_when_missing(self, store, persisted_user):
        settings = await store.get(persisted_user)
        assert settings.user_id == persisted_user
        assert settings.ui_theme == UITheme.SYSTEM
        assert settings.locale == "en-US"
        assert settings.timezone == "UTC"
        assert settings.notification_prefs == {}
        assert settings.dashboard_prefs == {}

    @pytest.mark.asyncio
    async def test_patch_updates_partial_fields(self, store, persisted_user):
        updated = await store.patch(
            persisted_user,
            UserSettingsPatch(
                ui_theme=UITheme.DARK,
                locale="pt-BR",
                notification_prefs={"email": False},
            ),
        )
        assert updated.ui_theme == UITheme.DARK
        assert updated.locale == "pt-BR"
        assert updated.timezone == "UTC"
        assert updated.notification_prefs == {"email": False}

    @pytest.mark.asyncio
    async def test_patch_creates_defaults_then_applies_update(self, store, persisted_user):
        updated = await store.patch(
            persisted_user,
            UserSettingsPatch(dashboard_prefs={"layout": "compact"}),
        )
        assert updated.ui_theme == UITheme.SYSTEM
        assert updated.dashboard_prefs == {"layout": "compact"}
