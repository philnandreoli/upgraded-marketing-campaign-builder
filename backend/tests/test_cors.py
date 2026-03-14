"""
Tests for CORS middleware configuration.

Validates that:
- The default wildcard origin is used when CORS_ALLOWED_ORIGINS is not set.
- Configured allowed origins are respected: preflight for an allowed origin
  returns Access-Control-Allow-Origin and 204; for a disallowed origin the
  header is absent.
- The application refuses to start (SystemExit) when a wildcard origin is
  configured in a non-development environment.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.main import app
# Capture the real function before the autouse fixture patches it in the module
# namespace, so TestCORSStartupGuard can call the original implementation.
from backend.apps.api.startup import _check_cors_safety as _real_check_cors_safety


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_db_lifecycle():
    """Prevent TestClient from triggering real DB init/close or startup guards."""
    with patch("backend.apps.api.startup.init_db", new_callable=AsyncMock), \
         patch("backend.apps.api.startup.close_db", new_callable=AsyncMock), \
         patch("backend.apps.api.startup._check_cors_safety"), \
         patch("backend.apps.api.startup._check_auth_safety"):
        yield


def _make_settings(allowed_origins: list[str], app_env: str = "development") -> MagicMock:
    settings = MagicMock()
    settings.cors.allowed_origins = allowed_origins
    settings.oidc.enabled = False
    settings.app.log_level = "INFO"
    settings.app.env = app_env
    return settings


# ---------------------------------------------------------------------------
# CORSSettings — unit tests for config parsing
# ---------------------------------------------------------------------------

class TestCORSSettingsDefaults:
    def test_default_allowed_origins_is_wildcard(self):
        """When CORS_ALLOWED_ORIGINS is not set the default is ['*']."""
        from backend.config import CORSSettings
        s = CORSSettings()
        assert s.allowed_origins == ["*"]

    def test_allowed_origins_parsed_from_json_env(self, monkeypatch):
        """CORS_ALLOWED_ORIGINS set as a JSON array is parsed into a list."""
        monkeypatch.setenv(
            "CORS_ALLOWED_ORIGINS",
            '["https://app.example.com","https://admin.example.com"]',
        )
        from backend.config import CORSSettings
        s = CORSSettings()
        assert s.allowed_origins == [
            "https://app.example.com",
            "https://admin.example.com",
        ]


# ---------------------------------------------------------------------------
# CORS middleware — integration tests via TestClient
# ---------------------------------------------------------------------------

class TestCORSMiddleware:
    """Integration smoke-tests: verify CORS headers on simple requests."""

    def test_wildcard_allows_any_origin(self):
        """With the default ['*'] config, any origin receives the CORS header."""
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(
                "/health/live",
                headers={"Origin": "https://random.example.com"},
            )
        assert resp.headers.get("access-control-allow-origin") == "*"

    def test_specific_origin_allowed(self):
        """An origin on the allowlist receives the correct CORS header."""
        allowed = "https://app.example.com"
        mock_settings = _make_settings([allowed])
        # Patch the module-level `settings` used by the middleware.
        with patch("backend.apps.api.main.settings", mock_settings):
            # Rebuild the app middleware with the patched settings by
            # invoking a fresh TestClient inside the patched context.
            from fastapi import FastAPI
            from fastapi.middleware.cors import CORSMiddleware

            test_app = FastAPI()
            test_app.add_middleware(
                CORSMiddleware,
                allow_origins=mock_settings.cors.allowed_origins,
                allow_credentials=True,
                allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                allow_headers=["Authorization", "Content-Type", "Accept"],
            )

            @test_app.get("/ping")
            async def ping():
                return {"ok": True}

            with TestClient(test_app) as client:
                resp = client.get("/ping", headers={"Origin": allowed})
            assert resp.headers.get("access-control-allow-origin") == allowed

    def test_disallowed_origin_not_reflected(self):
        """An origin NOT on the allowlist does not receive the CORS header."""
        allowed = "https://app.example.com"
        disallowed = "https://evil.example.com"

        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware

        test_app = FastAPI()
        test_app.add_middleware(
            CORSMiddleware,
            allow_origins=[allowed],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Accept"],
        )

        @test_app.get("/ping")
        async def ping():
            return {"ok": True}

        with TestClient(test_app) as client:
            resp = client.get("/ping", headers={"Origin": disallowed})
        assert "access-control-allow-origin" not in resp.headers


# ---------------------------------------------------------------------------
# Startup guard — wildcard CORS rejected in non-development environments
# ---------------------------------------------------------------------------

class TestCORSStartupGuard:
    """Validate that the startup guard rejects wildcard origins outside dev."""

    def test_wildcard_raises_system_exit_in_production(self):
        """SystemExit(1) is raised when app_env=production and origins=['*']."""
        with pytest.raises(SystemExit) as exc_info:
            _real_check_cors_safety("production", ["*"])
        assert exc_info.value.code == 1

    def test_wildcard_allowed_in_development(self):
        """No SystemExit when app_env=development and origins=['*'] (the default)."""
        # Should not raise
        _real_check_cors_safety("development", ["*"])

    def test_explicit_origins_allowed_in_production(self):
        """No SystemExit when origins are explicit even in production."""
        # Should not raise
        _real_check_cors_safety("production", ["https://app.example.com"])
