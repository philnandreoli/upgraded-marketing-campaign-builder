"""
Unit tests for the two-mode database authentication layer.

These tests cover:
  - _get_auth_mode()        — reads DB_AUTH_MODE env var
  - _build_azure_db_url()   — constructs the asyncpg URL from components
  - _fetch_entra_db_token() — acquires an Entra token via DefaultAzureCredential
  - _create_engine()        — creates the right engine for each mode
  - get_connection_dsn()    — returns the correct DSN for each mode
  - get_connection_password() — returns the token callable in azure mode
  - close_db()              — closes the Entra credential when open
  - DatabaseSettings        — validates config.py additions

No real database connection is required.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import backend.infrastructure.database as db_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_entra_credential():
    """Reset the module-level Entra credential before each test."""
    original = db_module._entra_credential
    db_module._entra_credential = None
    yield
    db_module._entra_credential = original


# ---------------------------------------------------------------------------
# _get_auth_mode
# ---------------------------------------------------------------------------

class TestGetAuthMode:
    def test_defaults_to_local(self, monkeypatch):
        monkeypatch.delenv("DB_AUTH_MODE", raising=False)
        assert db_module._get_auth_mode() == "local"

    def test_returns_azure_when_set(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        assert db_module._get_auth_mode() == "azure"

    def test_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "AZURE")
        assert db_module._get_auth_mode() == "azure"

    def test_unknown_mode_is_passed_through(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "custom")
        assert db_module._get_auth_mode() == "custom"


# ---------------------------------------------------------------------------
# _require_database_url
# ---------------------------------------------------------------------------

class TestRequireDatabaseUrl:
    def test_returns_url_when_set(self, monkeypatch):
        monkeypatch.setattr(
            db_module,
            "DATABASE_URL",
            "postgresql+asyncpg://user:pass@localhost:5432/db",
        )
        assert db_module._require_database_url() == (
            "postgresql+asyncpg://user:pass@localhost:5432/db"
        )

    def test_raises_when_database_url_is_empty(self, monkeypatch):
        monkeypatch.setattr(db_module, "DATABASE_URL", "")
        with pytest.raises(RuntimeError, match="DATABASE_URL environment variable is required"):
            db_module._require_database_url()

    def test_error_message_includes_example(self, monkeypatch):
        monkeypatch.setattr(db_module, "DATABASE_URL", "")
        with pytest.raises(RuntimeError, match="postgresql\\+asyncpg://"):
            db_module._require_database_url()


# ---------------------------------------------------------------------------
# _build_azure_db_url
# ---------------------------------------------------------------------------

class TestBuildAzureDbUrl:
    def test_builds_url_from_components(self, monkeypatch):
        monkeypatch.setenv("AZURE_POSTGRES_HOST", "myserver.postgres.database.azure.com")
        monkeypatch.setenv("AZURE_POSTGRES_DATABASE", "campaigns")
        monkeypatch.setenv("AZURE_POSTGRES_USER", "api-identity")
        url = db_module._build_azure_db_url()
        assert url == (
            "postgresql+asyncpg://api-identity"
            "@myserver.postgres.database.azure.com/campaigns"
        )

    def test_default_database_name(self, monkeypatch):
        monkeypatch.setenv("AZURE_POSTGRES_HOST", "myserver.postgres.database.azure.com")
        monkeypatch.delenv("AZURE_POSTGRES_DATABASE", raising=False)
        monkeypatch.setenv("AZURE_POSTGRES_USER", "api-identity")
        url = db_module._build_azure_db_url()
        assert url.endswith("/campaigns")

    def test_includes_asyncpg_driver(self, monkeypatch):
        monkeypatch.setenv("AZURE_POSTGRES_HOST", "host.postgres.database.azure.com")
        monkeypatch.setenv("AZURE_POSTGRES_DATABASE", "mydb")
        monkeypatch.setenv("AZURE_POSTGRES_USER", "worker")
        url = db_module._build_azure_db_url()
        assert url.startswith("postgresql+asyncpg://")


# ---------------------------------------------------------------------------
# _fetch_entra_db_token
# ---------------------------------------------------------------------------

class TestFetchEntraDbToken:
    async def test_returns_token_from_credential(self, monkeypatch):
        mock_token = MagicMock()
        mock_token.token = "test-access-token-abc"

        mock_cred = AsyncMock()
        mock_cred.get_token = AsyncMock(return_value=mock_token)

        # DefaultAzureCredential is imported lazily inside _fetch_entra_db_token;
        # patch where it is resolved.
        with patch("azure.identity.aio.DefaultAzureCredential", return_value=mock_cred):
            db_module._entra_credential = None
            token = await db_module._fetch_entra_db_token()

        assert token == "test-access-token-abc"

    async def test_reuses_existing_credential(self):
        """A second call must reuse the already-created credential object."""
        mock_token = MagicMock()
        mock_token.token = "reused-token"

        mock_cred = AsyncMock()
        mock_cred.get_token = AsyncMock(return_value=mock_token)

        # Pre-set the credential so _fetch_entra_db_token skips creation.
        db_module._entra_credential = mock_cred

        with patch("azure.identity.aio.DefaultAzureCredential") as mock_cls:
            token = await db_module._fetch_entra_db_token()
            # Constructor must NOT be called again.
            mock_cls.assert_not_called()

        assert token == "reused-token"
        mock_cred.get_token.assert_awaited_once_with(db_module._ENTRA_TOKEN_SCOPE)

    async def test_token_scope_is_postgres(self):
        assert db_module._ENTRA_TOKEN_SCOPE == (
            "https://ossrdbms-aad.database.windows.net/.default"
        )


# ---------------------------------------------------------------------------
# _create_engine
# ---------------------------------------------------------------------------

class TestCreateEngine:
    def test_local_mode_uses_database_url(self, monkeypatch):
        monkeypatch.delenv("DB_AUTH_MODE", raising=False)
        monkeypatch.setattr(
            db_module,
            "DATABASE_URL",
            "postgresql+asyncpg://testuser:testpass@localhost:5432/testdb",
        )
        with patch("backend.infrastructure.database.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()
            db_module._create_engine()
            args, kwargs = mock_create.call_args
        # Should use the DATABASE_URL, not azure URL
        assert "postgresql" in args[0]
        # No Entra connect_args in local mode
        assert "connect_args" not in kwargs
        # Pool configuration must be present
        assert kwargs.get("pool_size") == 10
        assert kwargs.get("max_overflow") == 20
        assert kwargs.get("pool_pre_ping") is True
        assert kwargs.get("pool_recycle") == 3600

    def test_azure_mode_uses_token_callable(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        monkeypatch.setenv("AZURE_POSTGRES_HOST", "myserver.postgres.database.azure.com")
        monkeypatch.setenv("AZURE_POSTGRES_DATABASE", "campaigns")
        monkeypatch.setenv("AZURE_POSTGRES_USER", "api-identity")
        with patch("backend.infrastructure.database.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()
            db_module._create_engine()
            args, kwargs = mock_create.call_args
        expected_url = (
            "postgresql+asyncpg://api-identity"
            "@myserver.postgres.database.azure.com/campaigns"
        )
        assert args[0] == expected_url
        connect_args = kwargs.get("connect_args", {})
        assert callable(connect_args.get("password"))
        assert connect_args.get("ssl") == "require"
        # Pool configuration must be present
        assert kwargs.get("pool_size") == 10
        assert kwargs.get("max_overflow") == 20
        assert kwargs.get("pool_pre_ping") is True
        assert kwargs.get("pool_recycle") == 3600

    def test_azure_mode_url_has_no_password_embedded(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        monkeypatch.setenv("AZURE_POSTGRES_HOST", "server.postgres.database.azure.com")
        monkeypatch.setenv("AZURE_POSTGRES_DATABASE", "db")
        monkeypatch.setenv("AZURE_POSTGRES_USER", "worker-id")
        with patch("backend.infrastructure.database.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()
            db_module._create_engine()
            args, _ = mock_create.call_args
        # Password must NOT be embedded in the URL
        assert ":" not in args[0].split("@")[0].replace("postgresql+asyncpg://", "")


# ---------------------------------------------------------------------------
# get_connection_dsn
# ---------------------------------------------------------------------------

class TestGetConnectionDsn:
    def test_local_mode_strips_asyncpg_prefix(self, monkeypatch):
        monkeypatch.delenv("DB_AUTH_MODE", raising=False)
        monkeypatch.setattr(
            db_module,
            "DATABASE_URL",
            "postgresql+asyncpg://testuser:testpass@localhost:5432/testdb",
        )
        dsn = db_module.get_connection_dsn()
        assert "postgresql+asyncpg" not in dsn
        assert dsn.startswith("postgresql://")

    def test_azure_mode_uses_azure_components(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        monkeypatch.setenv("AZURE_POSTGRES_HOST", "myserver.postgres.database.azure.com")
        monkeypatch.setenv("AZURE_POSTGRES_DATABASE", "campaigns")
        monkeypatch.setenv("AZURE_POSTGRES_USER", "api-identity")
        dsn = db_module.get_connection_dsn()
        assert dsn == (
            "postgresql://api-identity@myserver.postgres.database.azure.com/campaigns"
        )

    def test_azure_mode_no_password_in_dsn(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        monkeypatch.setenv("AZURE_POSTGRES_HOST", "server.postgres.database.azure.com")
        monkeypatch.setenv("AZURE_POSTGRES_DATABASE", "campaigns")
        monkeypatch.setenv("AZURE_POSTGRES_USER", "worker")
        dsn = db_module.get_connection_dsn()
        # No ":<password>@" pattern
        user_part = dsn.split("@")[0].replace("postgresql://", "")
        assert ":" not in user_part


# ---------------------------------------------------------------------------
# get_connection_password
# ---------------------------------------------------------------------------

class TestGetConnectionPassword:
    def test_local_mode_returns_none(self, monkeypatch):
        monkeypatch.delenv("DB_AUTH_MODE", raising=False)
        assert db_module.get_connection_password() is None

    def test_azure_mode_returns_callable(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        password = db_module.get_connection_password()
        assert callable(password)

    async def test_azure_mode_password_returns_token_string(self, monkeypatch):
        """The callable returned in azure mode must be awaitable and return a string."""
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        mock_token = MagicMock()
        mock_token.token = "az-token-xyz"
        mock_cred = AsyncMock()
        mock_cred.get_token = AsyncMock(return_value=mock_token)
        db_module._entra_credential = mock_cred

        password_fn = db_module.get_connection_password()
        assert password_fn is not None
        result = await password_fn()
        assert result == "az-token-xyz"


# ---------------------------------------------------------------------------
# close_db
# ---------------------------------------------------------------------------

class TestCloseDb:
    async def test_disposes_engine(self):
        mock_engine = AsyncMock()
        with patch.object(db_module, "engine", mock_engine):
            await db_module.close_db()
        mock_engine.dispose.assert_awaited_once()

    async def test_closes_entra_credential_when_set(self):
        mock_cred = AsyncMock()
        db_module._entra_credential = mock_cred

        mock_engine = AsyncMock()
        with patch.object(db_module, "engine", mock_engine):
            await db_module.close_db()

        mock_cred.close.assert_awaited_once()
        assert db_module._entra_credential is None

    async def test_close_db_with_no_credential_is_safe(self):
        db_module._entra_credential = None
        mock_engine = AsyncMock()
        with patch.object(db_module, "engine", mock_engine):
            await db_module.close_db()  # must not raise


# ---------------------------------------------------------------------------
# DatabaseSettings (config.py)
# ---------------------------------------------------------------------------

class TestDatabaseSettings:
    def test_defaults_to_local_mode(self, monkeypatch):
        monkeypatch.delenv("DB_AUTH_MODE", raising=False)
        from backend.config import DatabaseSettings
        settings = DatabaseSettings()
        assert settings.mode == "local"

    def test_azure_mode_from_env(self, monkeypatch):
        monkeypatch.setenv("DB_AUTH_MODE", "azure")
        from backend.config import DatabaseSettings
        settings = DatabaseSettings()
        assert settings.mode == "azure"

    def test_azure_host_from_env(self, monkeypatch):
        monkeypatch.setenv(
            "AZURE_POSTGRES_HOST", "myserver.postgres.database.azure.com"
        )
        from backend.config import DatabaseSettings
        settings = DatabaseSettings()
        assert settings.azure_host == "myserver.postgres.database.azure.com"

    def test_azure_database_default(self, monkeypatch):
        monkeypatch.delenv("AZURE_POSTGRES_DATABASE", raising=False)
        from backend.config import DatabaseSettings
        settings = DatabaseSettings()
        assert settings.azure_database == "campaigns"

    def test_azure_database_from_env(self, monkeypatch):
        monkeypatch.setenv("AZURE_POSTGRES_DATABASE", "mydb")
        from backend.config import DatabaseSettings
        settings = DatabaseSettings()
        assert settings.azure_database == "mydb"

    def test_azure_user_from_env(self, monkeypatch):
        monkeypatch.setenv("AZURE_POSTGRES_USER", "api-managed-identity")
        from backend.config import DatabaseSettings
        settings = DatabaseSettings()
        assert settings.azure_user == "api-managed-identity"

    def test_database_url_from_env(self, monkeypatch):
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+asyncpg://testuser:testpass@localhost:5432/testdb",
        )
        from backend.config import DatabaseSettings
        settings = DatabaseSettings()
        assert "testdb" in settings.url

    def test_database_settings_in_aggregate_settings(self):
        from backend.config import DatabaseSettings, Settings
        settings = Settings()
        assert isinstance(settings.database, DatabaseSettings)

    def test_auto_migrate_defaults_to_none(self, monkeypatch):
        monkeypatch.delenv("API_AUTO_MIGRATE", raising=False)
        from backend.config import DatabaseSettings
        settings = DatabaseSettings()
        assert settings.auto_migrate is None

    def test_auto_migrate_true_from_env(self, monkeypatch):
        monkeypatch.setenv("API_AUTO_MIGRATE", "true")
        from backend.config import DatabaseSettings
        settings = DatabaseSettings()
        assert settings.auto_migrate is True

    def test_auto_migrate_false_from_env(self, monkeypatch):
        monkeypatch.setenv("API_AUTO_MIGRATE", "false")
        from backend.config import DatabaseSettings
        settings = DatabaseSettings()
        assert settings.auto_migrate is False


# ---------------------------------------------------------------------------
# RedisSettings (config.py)
# ---------------------------------------------------------------------------

class TestRedisSettings:
    def test_defaults_to_local_mode(self, monkeypatch):
        monkeypatch.delenv("REDIS_MODE", raising=False)
        from backend.config import RedisSettings
        settings = RedisSettings()
        assert settings.mode == "local"

    def test_local_mode_default_url(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        from backend.config import RedisSettings
        settings = RedisSettings()
        assert settings.url == ""

    def test_local_url_from_env(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/1")
        from backend.config import RedisSettings
        settings = RedisSettings()
        assert settings.url == "redis://localhost:6379/1"

    def test_azure_mode_from_env(self, monkeypatch):
        monkeypatch.setenv("REDIS_MODE", "azure")
        from backend.config import RedisSettings
        settings = RedisSettings()
        assert settings.mode == "azure"

    def test_azure_host_from_env(self, monkeypatch):
        monkeypatch.setenv("AZURE_REDIS_HOST", "myredis.redis.cache.windows.net")
        from backend.config import RedisSettings
        settings = RedisSettings()
        assert settings.azure_host == "myredis.redis.cache.windows.net"

    def test_azure_port_default(self, monkeypatch):
        monkeypatch.delenv("AZURE_REDIS_PORT", raising=False)
        from backend.config import RedisSettings
        settings = RedisSettings()
        assert settings.azure_port == 6380

    def test_azure_port_from_env(self, monkeypatch):
        monkeypatch.setenv("AZURE_REDIS_PORT", "6381")
        from backend.config import RedisSettings
        settings = RedisSettings()
        assert settings.azure_port == 6381

    def test_azure_use_ssl_default(self, monkeypatch):
        monkeypatch.delenv("AZURE_REDIS_USE_SSL", raising=False)
        from backend.config import RedisSettings
        settings = RedisSettings()
        assert settings.azure_use_ssl is True

    def test_azure_use_ssl_false_from_env(self, monkeypatch):
        monkeypatch.setenv("AZURE_REDIS_USE_SSL", "false")
        from backend.config import RedisSettings
        settings = RedisSettings()
        assert settings.azure_use_ssl is False

    def test_redis_settings_in_aggregate_settings(self):
        from backend.config import RedisSettings, Settings
        settings = Settings()
        assert isinstance(settings.redis, RedisSettings)

    def test_redis_accessible_via_get_settings(self):
        from backend.config import RedisSettings, get_settings
        # Clear the lru_cache to get a fresh Settings instance
        get_settings.cache_clear()
        settings = get_settings()
        assert isinstance(settings.redis, RedisSettings)
        get_settings.cache_clear()
