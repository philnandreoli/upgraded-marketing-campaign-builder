"""
Tests for the Azure App Configuration bootstrap loader (backend/core/config_loader.py).

Covers:
- Successful load of plain key-value pairs from Azure App Configuration.
- Successful Key Vault reference resolution (handled natively by the provider).
- Failure behaviour when the App Configuration store cannot be loaded.
- Local fallback (no-op) when AZURE_APP_CONFIGURATION_ENDPOINT is not set.
- Process-environment override wins over App Configuration values.
- SystemExit on App Configuration load failure.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# load_azure_app_configuration
# ---------------------------------------------------------------------------


class TestLoadAzureAppConfiguration:
    """Tests for load_azure_app_configuration (mocks the Azure Provider SDK)."""

    def _make_provider(self, data: dict) -> MagicMock:
        """Return a mock that behaves like an AzureAppConfigurationProvider mapping."""
        mock_provider = MagicMock()
        mock_provider.items.return_value = data.items()
        return mock_provider

    def test_loads_plain_key_values(self):
        from backend.core.config_loader import load_azure_app_configuration

        provider_data = {
            "APP_ENV": "dev",
            "APP_PORT": "8000",
            "TRACING_ENABLED": "true",
        }
        mock_provider = self._make_provider(provider_data)

        with (
            patch("backend.core.config_loader.load", return_value=mock_provider) as mock_load,
            patch("backend.core.config_loader.DefaultAzureCredential"),
        ):
            result = load_azure_app_configuration(
                "https://appcs-dev-marketing.azconfig.io", "dev"
            )

        assert result == {
            "APP_ENV": "dev",
            "APP_PORT": "8000",
            "TRACING_ENABLED": "true",
        }
        mock_load.assert_called_once()
        call_kwargs = mock_load.call_args.kwargs
        assert call_kwargs["endpoint"] == "https://appcs-dev-marketing.azconfig.io"

    def test_key_vault_references_resolved_by_provider(self):
        """Key Vault references are resolved natively by the provider SDK — the caller
        simply receives the resolved plaintext value in the returned dict."""
        from backend.core.config_loader import load_azure_app_configuration

        # Provider has already resolved the KV reference; we get plaintext back
        provider_data = {
            "APP_ENV": "prod",
            "AZURE_CLIENT_SECRET": "resolved-secret-value",
        }
        mock_provider = self._make_provider(provider_data)

        with (
            patch("backend.core.config_loader.load", return_value=mock_provider),
            patch("backend.core.config_loader.DefaultAzureCredential"),
        ):
            result = load_azure_app_configuration(
                "https://appcs-prod-marketing.azconfig.io", "prod"
            )

        assert result["APP_ENV"] == "prod"
        assert result["AZURE_CLIENT_SECRET"] == "resolved-secret-value"

    def test_raises_on_provider_load_failure(self):
        """An exception raised by load() propagates to the caller."""
        from backend.core.config_loader import load_azure_app_configuration

        with (
            patch(
                "backend.core.config_loader.load",
                side_effect=RuntimeError("connection refused"),
            ),
            patch("backend.core.config_loader.DefaultAzureCredential"),
        ):
            with pytest.raises(RuntimeError, match="connection refused"):
                load_azure_app_configuration(
                    "https://appcs-prod-marketing.azconfig.io", "prod"
                )

    def test_none_value_stored_as_empty_string(self):
        from backend.core.config_loader import load_azure_app_configuration

        provider_data = {"OPTIONAL_KEY": None}
        mock_provider = self._make_provider(provider_data)

        with (
            patch("backend.core.config_loader.load", return_value=mock_provider),
            patch("backend.core.config_loader.DefaultAzureCredential"),
        ):
            result = load_azure_app_configuration(
                "https://appcs-dev-marketing.azconfig.io", "dev"
            )

        assert result["OPTIONAL_KEY"] == ""

    def test_uses_label_in_selector(self):
        """The label is passed via SettingSelector to the provider load() call."""
        from backend.core.config_loader import load_azure_app_configuration

        mock_provider = self._make_provider({})

        with (
            patch("backend.core.config_loader.load", return_value=mock_provider) as mock_load,
            patch("backend.core.config_loader.DefaultAzureCredential"),
        ):
            load_azure_app_configuration(
                "https://appcs-test-marketing.azconfig.io", "test"
            )

        call_kwargs = mock_load.call_args.kwargs
        selects = call_kwargs["selects"]
        assert len(selects) == 1
        assert selects[0].label_filter == "test"

    def test_passes_key_vault_options(self):
        """key_vault_options is passed to load() so the provider handles KV references."""
        from backend.core.config_loader import load_azure_app_configuration
        from azure.appconfiguration.provider import AzureAppConfigurationKeyVaultOptions

        mock_provider = self._make_provider({})

        with (
            patch("backend.core.config_loader.load", return_value=mock_provider) as mock_load,
            patch("backend.core.config_loader.DefaultAzureCredential"),
        ):
            load_azure_app_configuration(
                "https://appcs-dev-marketing.azconfig.io", "dev"
            )

        call_kwargs = mock_load.call_args.kwargs
        assert "key_vault_options" in call_kwargs
        assert isinstance(call_kwargs["key_vault_options"], AzureAppConfigurationKeyVaultOptions)


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
        monkeypatch.delenv("TRACING_ENABLED", raising=False)

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

    def test_blank_values_are_skipped(self, monkeypatch):
        """Blank App Configuration values are treated as unset and not injected."""
        monkeypatch.setenv("AZURE_APP_CONFIGURATION_ENDPOINT", "https://appcs.azconfig.io")
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.delenv("WS_AUTHZ_CACHE_TTL_SECONDS", raising=False)

        with patch(
            "backend.core.config_loader.load_azure_app_configuration",
            return_value={"WS_AUTHZ_CACHE_TTL_SECONDS": ""},
        ):
            from backend.core import config_loader

            config_loader.bootstrap_config()

        assert os.environ.get("WS_AUTHZ_CACHE_TTL_SECONDS") is None

    def test_blank_values_emit_warning_with_key_names(self, monkeypatch):
        """A warning is logged when blank values are skipped during injection."""
        monkeypatch.setenv("AZURE_APP_CONFIGURATION_ENDPOINT", "https://appcs.azconfig.io")
        monkeypatch.setenv("APP_ENV", "dev")

        with (
            patch(
                "backend.core.config_loader.load_azure_app_configuration",
                return_value={
                    "WS_AUTHZ_CACHE_TTL_SECONDS": "",
                    "WS_FANOUT_MAX_CONCURRENCY": "",
                },
            ),
            patch("backend.core.config_loader.logger.warning") as mock_warning,
        ):
            from backend.core import config_loader

            config_loader.bootstrap_config()

        mock_warning.assert_called_once()
        call_args = mock_warning.call_args[0]
        assert call_args[1] == 2
        assert "WS_AUTHZ_CACHE_TTL_SECONDS" in call_args[2]
        assert "WS_FANOUT_MAX_CONCURRENCY" in call_args[2]

    def test_blank_value_does_not_override_process_env(self, monkeypatch):
        """A blank App Configuration value must not clear an explicit process env value."""
        monkeypatch.setenv("AZURE_APP_CONFIGURATION_ENDPOINT", "https://appcs.azconfig.io")
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.setenv("WS_FANOUT_MAX_CONCURRENCY", "25")

        with patch(
            "backend.core.config_loader.load_azure_app_configuration",
            return_value={"WS_FANOUT_MAX_CONCURRENCY": ""},
        ):
            from backend.core import config_loader

            config_loader.bootstrap_config()

        assert os.environ.get("WS_FANOUT_MAX_CONCURRENCY") == "25"

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

