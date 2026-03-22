"""
Tests for the log redaction utilities and that sensitive campaign free-text
fields never appear in log output produced by the campaign API routes.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.log_utils import (
    SENSITIVE_BRIEF_FIELDS,
    redact_brief,
    safe_campaign_context,
)
from backend.models.campaign import CampaignBrief


# ---------------------------------------------------------------------------
# Unit tests for the helper functions in backend.core.log_utils
# ---------------------------------------------------------------------------


class TestRedactBrief:
    """redact_brief() must replace every SENSITIVE_BRIEF_FIELDS entry."""

    def _sample_brief_dict(self):
        return {
            "product_or_service": "SecretProduct X",
            "goal": "Double revenue in Q3",
            "budget": 50000.0,
            "currency": "USD",
            "start_date": "2026-04-01",
            "end_date": "2026-06-30",
            "additional_context": "Confidential go-to-market strategy",
            "selected_channels": ["email"],
            "social_media_platforms": [],
        }

    def test_sensitive_fields_are_redacted(self):
        result = redact_brief(self._sample_brief_dict())
        for field in SENSITIVE_BRIEF_FIELDS:
            assert result[field] == "[REDACTED]", f"Field '{field}' was not redacted"

    def test_sensitive_values_absent_from_result(self):
        brief = self._sample_brief_dict()
        result = redact_brief(brief)
        result_str = str(result)
        assert "SecretProduct X" not in result_str
        assert "Double revenue in Q3" not in result_str
        assert "Confidential go-to-market strategy" not in result_str

    def test_non_sensitive_fields_preserved(self):
        result = redact_brief(self._sample_brief_dict())
        assert result["budget"] == 50000.0
        assert result["currency"] == "USD"
        assert result["start_date"] == "2026-04-01"
        assert result["end_date"] == "2026-06-30"
        assert result["selected_channels"] == ["email"]

    def test_original_dict_not_mutated(self):
        brief = self._sample_brief_dict()
        original_product = brief["product_or_service"]
        redact_brief(brief)
        assert brief["product_or_service"] == original_product

    def test_empty_dict_returns_empty_dict(self):
        assert redact_brief({}) == {}

    def test_all_sensitive_fields_covered_by_constant(self):
        """Regression guard: every SENSITIVE_BRIEF_FIELDS entry is a real
        CampaignBrief field so the set stays in sync with the model."""
        model_fields = set(CampaignBrief.model_fields.keys())
        for field in SENSITIVE_BRIEF_FIELDS:
            assert field in model_fields, (
                f"SENSITIVE_BRIEF_FIELDS contains '{field}' which is not a "
                f"CampaignBrief field. Remove it or rename it."
            )


class TestSafeCampaignContext:
    """safe_campaign_context() must only include known-safe metadata keys."""

    _ALLOWED_KEYS = {"campaign_id", "workspace_id", "actor", "status"}

    def test_all_args_present(self):
        ctx = safe_campaign_context(
            campaign_id="c-1",
            workspace_id="ws-1",
            actor="user-1",
            status="draft",
        )
        assert ctx == {
            "campaign_id": "c-1",
            "workspace_id": "ws-1",
            "actor": "user-1",
            "status": "draft",
        }

    def test_only_allowed_keys_present(self):
        ctx = safe_campaign_context(
            campaign_id="c-1",
            workspace_id="ws-1",
            actor="user-1",
            status="draft",
        )
        assert set(ctx.keys()) <= self._ALLOWED_KEYS

    def test_none_args_excluded(self):
        ctx = safe_campaign_context(campaign_id="c-1")
        assert "workspace_id" not in ctx
        assert "actor" not in ctx
        assert "status" not in ctx

    def test_empty_call_returns_empty_dict(self):
        assert safe_campaign_context() == {}


# ---------------------------------------------------------------------------
# Integration-style tests: sensitive text must not appear in captured logs
# ---------------------------------------------------------------------------


class TestCreateCampaignLogging:
    """Verify that POST /campaigns never writes sensitive brief text to logs."""

    _SENSITIVE_TEXTS = [
        "MySecretProduct",
        "Triple sales in confidential region",
        "Top secret context info",
    ]

    @pytest.fixture(autouse=True)
    def _setup_store(self):
        """Minimal in-process store wiring (mirrors test_api_routes._isolated_store)."""
        import asyncio
        from fastapi.testclient import TestClient
        from backend.main import app
        from backend.infrastructure.auth import get_current_user
        from backend.models.user import User, UserRole
        from backend.models.workspace import WorkspaceRole
        from backend.tests.mock_store import InMemoryCampaignStore

        self._user = User(
            id="log-test-user",
            email="log@test.com",
            display_name="Log Tester",
            roles=[UserRole.CAMPAIGN_BUILDER],
        )
        self._ws_id = "log-test-ws-001"

        fresh_store = InMemoryCampaignStore()
        mock_executor = MagicMock()
        mock_executor.dispatch = AsyncMock()

        async def _setup():
            ws = await fresh_store.create_workspace(
                name="Log Test WS", owner_id=self._user.id
            )
            ws.id = self._ws_id
            fresh_store._workspaces = {self._ws_id: ws}
            fresh_store._workspace_members = {
                (self._ws_id, self._user.id): WorkspaceRole.CREATOR.value
            }

        asyncio.get_event_loop().run_until_complete(_setup())

        with (
            patch("backend.api.campaigns.get_campaign_store", return_value=fresh_store),
            patch(
                "backend.apps.api.dependencies.get_campaign_store",
                return_value=fresh_store,
            ),
            patch(
                "backend.api.campaign_members.get_campaign_store",
                return_value=fresh_store,
            ),
            patch(
                "backend.application.campaign_workflow_service.get_campaign_store",
                return_value=fresh_store,
            ),
            patch(
                "backend.application.campaign_workflow_service._workflow_service",
                None,
            ),
            patch(
                "backend.api.campaigns.get_executor", return_value=mock_executor
            ),
            patch(
                "backend.api.campaign_workflow.get_executor",
                return_value=mock_executor,
            ),
            patch("backend.apps.api.startup.init_db", new_callable=AsyncMock),
            patch("backend.apps.api.startup.close_db", new_callable=AsyncMock),
        ):
            app.dependency_overrides[get_current_user] = lambda: self._user
            self._client = TestClient(app, raise_server_exceptions=False)
            yield
            app.dependency_overrides.pop(get_current_user, None)

    def test_sensitive_brief_text_not_in_log_records(self, caplog):
        """Sensitive brief fields must not appear in any log record emitted
        during campaign creation."""
        payload = {
            "product_or_service": self._SENSITIVE_TEXTS[0],
            "goal": self._SENSITIVE_TEXTS[1],
            "additional_context": self._SENSITIVE_TEXTS[2],
            "budget": 10000,
            "currency": "USD",
        }

        with caplog.at_level(logging.DEBUG, logger="backend"):
            resp = self._client.post(
                f"/api/workspaces/{self._ws_id}/campaigns",
                json=payload,
            )

        assert resp.status_code == 201, resp.text

        all_log_text = " ".join(r.getMessage() for r in caplog.records)
        for sensitive in self._SENSITIVE_TEXTS:
            assert sensitive not in all_log_text, (
                f"Sensitive text '{sensitive}' was found in log output: "
                f"{all_log_text!r}"
            )

    def test_metadata_present_in_log_records(self, caplog):
        """Campaign creation logs must still include non-sensitive metadata
        (workspace_id, actor, campaign_id, status) so logs are useful."""
        payload = {
            "product_or_service": "Product Name",
            "goal": "Campaign Goal",
            "budget": 5000,
            "currency": "USD",
        }

        with caplog.at_level(logging.INFO, logger="backend.api.campaigns"):
            resp = self._client.post(
                f"/api/workspaces/{self._ws_id}/campaigns",
                json=payload,
            )

        assert resp.status_code == 201, resp.text
        campaign_id = resp.json()["id"]

        all_log_text = " ".join(r.getMessage() for r in caplog.records)

        # workspace_id, actor and campaign_id must appear
        assert self._ws_id in all_log_text
        assert self._user.id in all_log_text
        assert campaign_id in all_log_text
