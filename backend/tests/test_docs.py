"""Tests for custom docs HTML generation."""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.apps.api.docs import register_custom_docs


def _make_app() -> FastAPI:
    app = FastAPI(
        title="Test App",
        docs_url=None,
        redoc_url=None,
    )
    register_custom_docs(app)
    return app


def test_docs_disables_persist_authorization_outside_development():
    settings = MagicMock()
    settings.app.env = "production"
    with patch("backend.apps.api.docs.get_settings", return_value=settings):
        with TestClient(_make_app()) as client:
            response = client.get("/docs")
        assert response.status_code == 200
        assert "persistAuthorization: false" in response.text


def test_docs_enables_persist_authorization_in_development():
    settings = MagicMock()
    settings.app.env = "development"
    with patch("backend.apps.api.docs.get_settings", return_value=settings):
        with TestClient(_make_app()) as client:
            response = client.get("/docs")
        assert response.status_code == 200
        assert "persistAuthorization: true" in response.text
