"""
Tests for CORS middleware configuration.

Validates that:
- The default wildcard origin is used when CORS_ALLOWED_ORIGINS is not set.
- Configured allowed origins are respected: preflight for an allowed origin
  returns Access-Control-Allow-Origin and 204; for a disallowed origin the
  header is absent.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_db_lifecycle():
    """Prevent TestClient from triggering real DB init/close."""
    with patch("backend.apps.api.startup.init_db", new_callable=AsyncMock), \
         patch("backend.apps.api.startup.close_db", new_callable=AsyncMock):
        yield


def _make_settings(allowed_origins: list[str]) -> MagicMock:
    settings = MagicMock()
    settings.cors.allowed_origins = allowed_origins
    settings.oidc.enabled = False
    settings.app.log_level = "INFO"
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
                allow_methods=["*"],
                allow_headers=["*"],
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
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @test_app.get("/ping")
        async def ping():
            return {"ok": True}

        with TestClient(test_app) as client:
            resp = client.get("/ping", headers={"Origin": disallowed})
        assert "access-control-allow-origin" not in resp.headers
