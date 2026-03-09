"""
Tests for the schema migration boundary separation.

Covers:
  - init_db() dispatches to the correct strategy based on DB_AUTH_MODE
  - init_db() honours the explicit API_AUTO_MIGRATE override
  - _should_auto_migrate() — default derivation and explicit override
  - _verify_schema_at_head() passes when DB is at head and raises when not
  - backend.apps.migrate.main — run_migrations() and main() entrypoint
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

import backend.infrastructure.database as db_module


# ---------------------------------------------------------------------------
# _should_auto_migrate()
# ---------------------------------------------------------------------------

class TestShouldAutoMigrate:
    """_should_auto_migrate() derives the correct default and respects overrides."""

    def test_local_mode_defaults_to_true(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "local")
        monkeypatch.delenv("API_AUTO_MIGRATE", raising=False)
        assert db_module._should_auto_migrate() is True

    def test_azure_mode_defaults_to_false(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        monkeypatch.delenv("API_AUTO_MIGRATE", raising=False)
        assert db_module._should_auto_migrate() is False

    def test_unset_db_auth_mode_defaults_to_true(self, monkeypatch):
        monkeypatch.delenv("DB_AUTH_MODE", raising=False)
        monkeypatch.delenv("API_AUTO_MIGRATE", raising=False)
        assert db_module._should_auto_migrate() is True

    def test_explicit_true_overrides_azure_mode(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        monkeypatch.setenv("API_AUTO_MIGRATE", "true")
        assert db_module._should_auto_migrate() is True

    def test_explicit_false_overrides_local_mode(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "local")
        monkeypatch.setenv("API_AUTO_MIGRATE", "false")
        assert db_module._should_auto_migrate() is False

    def test_accepts_1_as_true(self, monkeypatch):
        monkeypatch.setenv("API_AUTO_MIGRATE", "1")
        assert db_module._should_auto_migrate() is True

    def test_accepts_yes_as_true(self, monkeypatch):
        monkeypatch.setenv("API_AUTO_MIGRATE", "yes")
        assert db_module._should_auto_migrate() is True

    def test_accepts_0_as_false(self, monkeypatch):
        monkeypatch.setenv("API_AUTO_MIGRATE", "0")
        assert db_module._should_auto_migrate() is False

    def test_explicit_flag_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("API_AUTO_MIGRATE", "TRUE")
        assert db_module._should_auto_migrate() is True

    def test_explicit_flag_strips_whitespace(self, monkeypatch):
        monkeypatch.setenv("API_AUTO_MIGRATE", "  false  ")
        assert db_module._should_auto_migrate() is False


# ---------------------------------------------------------------------------
# init_db() dispatch
# ---------------------------------------------------------------------------

class TestInitDbDispatch:
    """init_db() must call the correct helper based on _should_auto_migrate()."""

    async def test_local_mode_runs_migrations(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "local")
        monkeypatch.delenv("API_AUTO_MIGRATE", raising=False)
        with patch.object(db_module, "_run_migrations", new_callable=AsyncMock) as mock_run, \
             patch.object(db_module, "_verify_schema_at_head", new_callable=AsyncMock) as mock_verify:
            await db_module.init_db()
        mock_run.assert_awaited_once()
        mock_verify.assert_not_called()

    async def test_azure_mode_verifies_schema(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        monkeypatch.delenv("API_AUTO_MIGRATE", raising=False)
        with patch.object(db_module, "_run_migrations", new_callable=AsyncMock) as mock_run, \
             patch.object(db_module, "_verify_schema_at_head", new_callable=AsyncMock) as mock_verify:
            await db_module.init_db()
        mock_verify.assert_awaited_once()
        mock_run.assert_not_called()

    async def test_default_mode_runs_migrations(self, monkeypatch):
        monkeypatch.delenv("DB_AUTH_MODE", raising=False)
        monkeypatch.delenv("API_AUTO_MIGRATE", raising=False)
        with patch.object(db_module, "_run_migrations", new_callable=AsyncMock) as mock_run, \
             patch.object(db_module, "_verify_schema_at_head", new_callable=AsyncMock) as mock_verify:
            await db_module.init_db()
        mock_run.assert_awaited_once()
        mock_verify.assert_not_called()

    async def test_explicit_false_disables_migration_in_local_mode(self, monkeypatch):
        """API_AUTO_MIGRATE=false must disable auto-migration even in local DB mode."""
        monkeypatch.setenv("DB_AUTH_MODE", "local")
        monkeypatch.setenv("API_AUTO_MIGRATE", "false")
        with patch.object(db_module, "_run_migrations", new_callable=AsyncMock) as mock_run, \
             patch.object(db_module, "_verify_schema_at_head", new_callable=AsyncMock) as mock_verify:
            await db_module.init_db()
        mock_verify.assert_awaited_once()
        mock_run.assert_not_called()

    async def test_explicit_true_enables_migration_in_azure_mode(self, monkeypatch):
        """API_AUTO_MIGRATE=true must enable auto-migration even in azure DB mode."""
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        monkeypatch.setenv("API_AUTO_MIGRATE", "true")
        with patch.object(db_module, "_run_migrations", new_callable=AsyncMock) as mock_run, \
             patch.object(db_module, "_verify_schema_at_head", new_callable=AsyncMock) as mock_verify:
            await db_module.init_db()
        mock_run.assert_awaited_once()
        mock_verify.assert_not_called()


# ---------------------------------------------------------------------------
# _verify_schema_at_head()
# ---------------------------------------------------------------------------

class TestVerifySchemaAtHead:
    """_verify_schema_at_head() should pass when at head and raise when not."""

    def _make_mock_engine(self, version_num: str | None):
        """Return a mock async engine that yields *version_num* from alembic_version."""
        row = (version_num,) if version_num is not None else None
        mock_result = MagicMock()
        mock_result.fetchone.return_value = row

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_result)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        return mock_engine

    async def test_passes_when_at_head(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        monkeypatch.setenv("AZURE_POSTGRES_HOST", "server.postgres.database.azure.com")
        monkeypatch.setenv("AZURE_POSTGRES_DATABASE", "campaigns")
        monkeypatch.setenv("AZURE_POSTGRES_USER", "migration-id")

        mock_script = MagicMock()
        mock_script.get_current_head.return_value = "0009"

        mock_engine = self._make_mock_engine("0009")

        with patch("alembic.script.ScriptDirectory") as MockSd, \
             patch.object(db_module, "engine", mock_engine), \
             patch.object(db_module, "_make_alembic_config", return_value=MagicMock()):
            MockSd.from_config.return_value = mock_script
            # Should not raise
            await db_module._verify_schema_at_head()

    async def test_raises_when_behind_head(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        monkeypatch.setenv("AZURE_POSTGRES_HOST", "server.postgres.database.azure.com")
        monkeypatch.setenv("AZURE_POSTGRES_DATABASE", "campaigns")
        monkeypatch.setenv("AZURE_POSTGRES_USER", "migration-id")

        mock_script = MagicMock()
        mock_script.get_current_head.return_value = "0009"

        mock_engine = self._make_mock_engine("0007")

        with patch("alembic.script.ScriptDirectory") as MockSd, \
             patch.object(db_module, "engine", mock_engine), \
             patch.object(db_module, "_make_alembic_config", return_value=MagicMock()):
            MockSd.from_config.return_value = mock_script
            with pytest.raises(RuntimeError, match="Database schema mismatch"):
                await db_module._verify_schema_at_head()

    async def test_raises_when_no_version_row(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        monkeypatch.setenv("AZURE_POSTGRES_HOST", "server.postgres.database.azure.com")
        monkeypatch.setenv("AZURE_POSTGRES_DATABASE", "campaigns")
        monkeypatch.setenv("AZURE_POSTGRES_USER", "migration-id")

        mock_script = MagicMock()
        mock_script.get_current_head.return_value = "0009"

        mock_engine = self._make_mock_engine(None)  # empty alembic_version table

        with patch("alembic.script.ScriptDirectory") as MockSd, \
             patch.object(db_module, "engine", mock_engine), \
             patch.object(db_module, "_make_alembic_config", return_value=MagicMock()):
            MockSd.from_config.return_value = mock_script
            with pytest.raises(RuntimeError, match="Database schema mismatch"):
                await db_module._verify_schema_at_head()

    async def test_raises_when_db_query_fails(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        monkeypatch.setenv("AZURE_POSTGRES_HOST", "server.postgres.database.azure.com")
        monkeypatch.setenv("AZURE_POSTGRES_DATABASE", "campaigns")
        monkeypatch.setenv("AZURE_POSTGRES_USER", "migration-id")

        mock_script = MagicMock()
        mock_script.get_current_head.return_value = "0009"

        # Engine raises — e.g. table doesn't exist on a fresh DB
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(side_effect=Exception("relation does not exist"))
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch("alembic.script.ScriptDirectory") as MockSd, \
             patch.object(db_module, "engine", mock_engine), \
             patch.object(db_module, "_make_alembic_config", return_value=MagicMock()):
            MockSd.from_config.return_value = mock_script
            with pytest.raises(RuntimeError, match="Unable to read schema version"):
                await db_module._verify_schema_at_head()


# ---------------------------------------------------------------------------
# backend.apps.migrate.main
# ---------------------------------------------------------------------------

class TestMigrateMain:
    """Tests for the dedicated migration entry point."""

    def test_run_migrations_calls_alembic_upgrade(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "local")

        from backend.apps.migrate.main import run_migrations

        mock_cfg = MagicMock()
        mock_upgrade = MagicMock()

        with patch("backend.apps.migrate.main._make_alembic_config", return_value=mock_cfg), \
             patch("alembic.command.upgrade", mock_upgrade):
            run_migrations()

        mock_upgrade.assert_called_once_with(mock_cfg, "head")

    def test_main_exits_zero_on_success(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "local")

        from backend.apps.migrate.main import main

        with patch("backend.apps.migrate.main.run_migrations") as mock_run:
            # Should not call sys.exit
            main()
        mock_run.assert_called_once()

    def test_main_exits_one_on_failure(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "local")

        from backend.apps.migrate.main import main

        with patch("backend.apps.migrate.main.run_migrations", side_effect=RuntimeError("boom")):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 1

    def test_make_alembic_config_sets_script_location(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "local")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/campaigns")

        from backend.apps.migrate.main import _make_alembic_config

        with patch("alembic.config.Config") as MockConfig:
            mock_cfg = MagicMock()
            MockConfig.return_value = mock_cfg
            _make_alembic_config()

        # set_main_option should have been called for script_location
        calls = [str(c) for c in mock_cfg.set_main_option.call_args_list]
        assert any("script_location" in c for c in calls), (
            "Expected set_main_option('script_location', ...) to be called"
        )

    def test_make_alembic_config_azure_sets_azure_url(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        monkeypatch.setenv("AZURE_POSTGRES_HOST", "srv.postgres.database.azure.com")
        monkeypatch.setenv("AZURE_POSTGRES_DATABASE", "campaigns")
        monkeypatch.setenv("AZURE_POSTGRES_USER", "migration-id")

        from backend.apps.migrate.main import _make_alembic_config

        with patch("alembic.config.Config") as MockConfig:
            mock_cfg = MagicMock()
            MockConfig.return_value = mock_cfg
            _make_alembic_config()

        url_calls = [
            c for c in mock_cfg.set_main_option.call_args_list
            if c.args[0] == "sqlalchemy.url"
        ]
        assert url_calls, "sqlalchemy.url must be set in azure mode"
        url_value = url_calls[0].args[1]
        # URL must follow "protocol://user@host/db" — validate host and no embedded password
        from urllib.parse import urlparse
        parsed = urlparse(url_value)
        assert parsed.hostname == "srv.postgres.database.azure.com"
        assert parsed.password is None, "No password should be embedded in the azure URL"
