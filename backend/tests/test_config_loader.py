"""
Tests for the Azure App Configuration bootstrap loader (backend/core/config_loader.py).

Covers:
- Successful load of plain key-value pairs from Azure App Configuration.
- Successful Key Vault reference resolution.
- Failure behaviour when a Key Vault reference cannot be resolved.
- Local fallback (no-op) when AZURE_APP_CONFIGURATION_ENDPOINT is not set.
- Process-environment override wins over App Configuration values.
- SystemExit on App Configuration load failure.
- Invalid Key Vault URI format raises ValueError.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


def _make_kv(key: str, value: str, content_type: str = "") -> SimpleNamespace:
    """Return a lightweight mock of an Azure App Configuration ConfigurationSetting."""
    return SimpleNamespace(key=key, value=value, content_type=content_type)


def _make_kv_ref(key: str, vault_uri: str) -> SimpleNamespace:
    """Return a Key Vault reference setting mock."""
    return _make_kv(
        key=key,
        value=json.dumps({"uri": vault_uri}),
        content_type="application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8",
    )


# ---------------------------------------------------------------------------
# _resolve_keyvault_reference
# ---------------------------------------------------------------------------


class TestResolveKeyvaultReference:
    """Unit tests for the internal Key Vault reference resolver."""

    def test_resolves_secret_without_version(self):
        from backend.core.config_loader import _resolve_keyvault_reference

        mock_secret = MagicMock()
        mock_secret.value = "supersecret"
        mock_client = MagicMock()
        mock_client.get_secret.return_value = mock_secret

        with patch(
            "backend.core.config_loader.SecretClient", return_value=mock_client
        ):
            result = _resolve_keyvault_reference(
                "https://myvault.vault.azure.net/secrets/mysecret",
                MagicMock(),
            )

        assert result == "supersecret"
        mock_client.get_secret.assert_called_once_with("mysecret", version=None)

    def test_resolves_secret_with_version(self):
        from backend.core.config_loader import _resolve_keyvault_reference

        mock_secret = MagicMock()
        mock_secret.value = "versioned-value"
        mock_client = MagicMock()
        mock_client.get_secret.return_value = mock_secret

        with patch(
            "backend.core.config_loader.SecretClient", return_value=mock_client
        ):
            result = _resolve_keyvault_reference(
                "https://myvault.vault.azure.net/secrets/mysecret/abc123version",
                MagicMock(),
            )

        assert result == "versioned-value"
        mock_client.get_secret.assert_called_once_with(
            "mysecret", version="abc123version"
        )

    def test_raises_value_error_for_invalid_uri(self):
        from backend.core.config_loader import _resolve_keyvault_reference

        with pytest.raises(ValueError, match="Unexpected Key Vault secret URI format"):
            _resolve_keyvault_reference(
                "https://myvault.vault.azure.net/keys/mykey",
                MagicMock(),
            )

    def test_raises_value_error_for_missing_secret_name(self):
        from backend.core.config_loader import _resolve_keyvault_reference

        with pytest.raises(ValueError, match="Unexpected Key Vault secret URI format"):
            _resolve_keyvault_reference(
                "https://myvault.vault.azure.net/secrets/",
                MagicMock(),
            )


# ---------------------------------------------------------------------------
# load_azure_app_configuration
# ---------------------------------------------------------------------------


class TestLoadAzureAppConfiguration:
    """Tests for load_azure_app_configuration (mocks the Azure SDK)."""

    def _patch_sdk(self, settings_list, monkeypatch=None):
        """Return context managers that patch the Azure SDK with given setting list."""
        mock_client = MagicMock()
        mock_client.list_configuration_settings.return_value = iter(settings_list)
        mock_app_config_class = MagicMock(return_value=mock_client)
        mock_credential = MagicMock()
        return mock_app_config_class, mock_credential, mock_client

    def test_loads_plain_key_values(self):
        from backend.core.config_loader import load_azure_app_configuration

        settings = [
            _make_kv("APP_ENV", "dev"),
            _make_kv("APP_PORT", "8000"),
            _make_kv("TRACING_ENABLED", "true"),
        ]
        mock_client_class, mock_cred, mock_client = self._patch_sdk(settings)

        with (
            patch(
                "backend.core.config_loader.AzureAppConfigurationClient",
                mock_client_class,
            ),
            patch(
                "backend.core.config_loader.DefaultAzureCredential",
                return_value=mock_cred,
            ),
        ):
            result = load_azure_app_configuration(
                "https://appcs-dev-marketing.azconfig.io", "dev"
            )

        assert result == {
            "APP_ENV": "dev",
            "APP_PORT": "8000",
            "TRACING_ENABLED": "true",
        }
        mock_client.list_configuration_settings.assert_called_once_with(
            label_filter="dev"
        )

    def test_resolves_keyvault_references(self):
        from backend.core.config_loader import load_azure_app_configuration

        settings = [
            _make_kv("APP_ENV", "prod"),
            _make_kv_ref(
                "AZURE_CLIENT_SECRET",
                "https://myvault.vault.azure.net/secrets/client-secret",
            ),
        ]
        mock_client_class, mock_cred, mock_client = self._patch_sdk(settings)

        mock_secret = MagicMock()
        mock_secret.value = "resolved-secret-value"
        mock_kv_client = MagicMock()
        mock_kv_client.get_secret.return_value = mock_secret

        with (
            patch(
                "backend.core.config_loader.AzureAppConfigurationClient",
                mock_client_class,
            ),
            patch(
                "backend.core.config_loader.DefaultAzureCredential",
                return_value=mock_cred,
            ),
            patch(
                "backend.core.config_loader.SecretClient",
                return_value=mock_kv_client,
            ),
        ):
            result = load_azure_app_configuration(
                "https://appcs-prod-marketing.azconfig.io", "prod"
            )

        assert result["APP_ENV"] == "prod"
        assert result["AZURE_CLIENT_SECRET"] == "resolved-secret-value"

    def test_raises_runtime_error_on_unresolvable_kv_reference(self):
        from backend.core.config_loader import load_azure_app_configuration

        settings = [
            _make_kv_ref(
                "MISSING_SECRET",
                "https://myvault.vault.azure.net/secrets/does-not-exist",
            ),
        ]
        mock_client_class, mock_cred, mock_client = self._patch_sdk(settings)

        mock_kv_client = MagicMock()
        mock_kv_client.get_secret.side_effect = Exception("SecretNotFound")

        with (
            patch(
                "backend.core.config_loader.AzureAppConfigurationClient",
                mock_client_class,
            ),
            patch(
                "backend.core.config_loader.DefaultAzureCredential",
                return_value=mock_cred,
            ),
            patch(
                "backend.core.config_loader.SecretClient",
                return_value=mock_kv_client,
            ),
        ):
            with pytest.raises(RuntimeError, match="failed to resolve Key Vault reference"):
                load_azure_app_configuration(
                    "https://appcs-prod-marketing.azconfig.io", "prod"
                )

    def test_none_value_stored_as_empty_string(self):
        from backend.core.config_loader import load_azure_app_configuration

        settings = [_make_kv("OPTIONAL_KEY", None)]  # type: ignore[arg-type]
        mock_client_class, mock_cred, mock_client = self._patch_sdk(settings)

        with (
            patch(
                "backend.core.config_loader.AzureAppConfigurationClient",
                mock_client_class,
            ),
            patch(
                "backend.core.config_loader.DefaultAzureCredential",
                return_value=mock_cred,
            ),
        ):
            result = load_azure_app_configuration(
                "https://appcs-dev-marketing.azconfig.io", "dev"
            )

        assert result["OPTIONAL_KEY"] == ""

    def test_uses_label_filter(self):
        from backend.core.config_loader import load_azure_app_configuration

        mock_client_class, mock_cred, mock_client = self._patch_sdk([])
        mock_client.list_configuration_settings.return_value = iter([])

        with (
            patch(
                "backend.core.config_loader.AzureAppConfigurationClient",
                mock_client_class,
            ),
            patch(
                "backend.core.config_loader.DefaultAzureCredential",
                return_value=mock_cred,
            ),
        ):
            load_azure_app_configuration(
                "https://appcs-test-marketing.azconfig.io", "test"
            )

        mock_client.list_configuration_settings.assert_called_once_with(
            label_filter="test"
        )


# ---------------------------------------------------------------------------
# bootstrap_config
# ---------------------------------------------------------------------------


class TestBootstrapConfig:
    """Tests for the top-level bootstrap_config() function."""

    def test_noop_when_endpoint_not_set(self, monkeypatch):
        """No Azure calls made when AZURE_APP_CONFIGURATION_ENDPOINT is absent."""
        monkeypatch.delenv("AZURE_APP_CONFIGURATION_ENDPOINT", raising=False)

        with patch(
            "backend.core.config_loader.load_azure_app_configuration"
        ) as mock_load:
            from backend.core.config_loader import bootstrap_config

            bootstrap_config()

        mock_load.assert_not_called()

    def test_injects_loaded_settings_into_os_environ(self, monkeypatch):
        """Values from App Configuration are injected into os.environ."""
        monkeypatch.setenv("AZURE_APP_CONFIGURATION_ENDPOINT", "https://appcs.azconfig.io")
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.delenv("APP_PORT", raising=False)

        with patch(
            "backend.core.config_loader.load_azure_app_configuration",
            return_value={"APP_PORT": "9000", "TRACING_ENABLED": "true"},
        ):
            from backend.core import config_loader

            config_loader.bootstrap_config()

        assert os.environ.get("APP_PORT") == "9000"
        assert os.environ.get("TRACING_ENABLED") == "true"

    def test_process_env_overrides_app_configuration(self, monkeypatch):
        """Explicit process env variables are not overwritten by App Configuration values."""
        monkeypatch.setenv("AZURE_APP_CONFIGURATION_ENDPOINT", "https://appcs.azconfig.io")
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.setenv("APP_PORT", "8888")  # already set — should NOT be overwritten

        with patch(
            "backend.core.config_loader.load_azure_app_configuration",
            return_value={"APP_PORT": "9000"},
        ):
            from backend.core import config_loader

            config_loader.bootstrap_config()

        # Process env value wins
        assert os.environ.get("APP_PORT") == "8888"

    def test_system_exit_on_load_failure(self, monkeypatch):
        """SystemExit(1) is raised when App Configuration cannot be loaded."""
        monkeypatch.setenv(
            "AZURE_APP_CONFIGURATION_ENDPOINT", "https://appcs.azconfig.io"
        )
        monkeypatch.setenv("APP_ENV", "dev")

        with patch(
            "backend.core.config_loader.load_azure_app_configuration",
            side_effect=RuntimeError("connection refused"),
        ):
            from backend.core import config_loader

            with pytest.raises(SystemExit) as exc_info:
                config_loader.bootstrap_config()

        assert exc_info.value.code == 1

    def test_uses_app_env_as_label(self, monkeypatch):
        """APP_ENV value is used as the label when querying App Configuration."""
        monkeypatch.setenv("AZURE_APP_CONFIGURATION_ENDPOINT", "https://appcs.azconfig.io")
        monkeypatch.setenv("APP_ENV", "prod")

        with patch(
            "backend.core.config_loader.load_azure_app_configuration",
            return_value={},
        ) as mock_load:
            from backend.core import config_loader

            config_loader.bootstrap_config()

        mock_load.assert_called_once_with("https://appcs.azconfig.io", "prod")

    def test_defaults_label_to_development_when_app_env_absent(self, monkeypatch):
        """When APP_ENV is not set the label defaults to 'development'."""
        monkeypatch.setenv("AZURE_APP_CONFIGURATION_ENDPOINT", "https://appcs.azconfig.io")
        monkeypatch.delenv("APP_ENV", raising=False)

        with patch(
            "backend.core.config_loader.load_azure_app_configuration",
            return_value={},
        ) as mock_load:
            from backend.core import config_loader

            config_loader.bootstrap_config()

        mock_load.assert_called_once_with("https://appcs.azconfig.io", "development")
