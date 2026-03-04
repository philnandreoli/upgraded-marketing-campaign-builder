"""
Tests for WebSocket authentication and authorization.

Validates that:
- Connections succeed when auth is disabled (local-dev)
- Connections are rejected with 4001 when a token is missing/invalid (auth enabled)
- Connections to campaign-specific WS are rejected with 4003 when the user is
  not a member of that campaign
- Admins can connect to any campaign without membership
- Campaign members can connect
- Global broadcast filters events by campaign membership for non-admin users
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from fastapi import WebSocketDisconnect

from backend.main import app
from backend.models.user import User, UserRole, CampaignMemberRole
from backend.tests.mock_store import InMemoryCampaignStore


# ---------------------------------------------------------------------------
# Shared test users
# ---------------------------------------------------------------------------

_ADMIN = User(id="admin-1", email="admin@example.com", roles=[UserRole.ADMIN])
_MEMBER = User(id="member-1", email="member@example.com", roles=[UserRole.CAMPAIGN_BUILDER])
_OUTSIDER = User(id="outsider-1", email="outsider@example.com", roles=[UserRole.VIEWER])

_CAMPAIGN_ID = "campaign-abc"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_db_lifecycle():
    """Prevent TestClient from calling real init_db / close_db."""
    with patch("backend.main.init_db", new_callable=AsyncMock), \
         patch("backend.main.close_db", new_callable=AsyncMock):
        yield


@pytest.fixture
def fresh_store():
    store = InMemoryCampaignStore()
    store._members[(_CAMPAIGN_ID, _MEMBER.id)] = CampaignMemberRole.VIEWER.value
    return store


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_enabled_settings():
    """Return a mock Settings object with auth enabled."""
    settings = MagicMock()
    settings.oidc.enabled = True
    return settings


def _auth_disabled_settings():
    """Return a mock Settings object with auth disabled."""
    settings = MagicMock()
    settings.oidc.enabled = False
    return settings


# ---------------------------------------------------------------------------
# ws_campaign — auth disabled (local-dev)
# ---------------------------------------------------------------------------

class TestWsCampaignAuthDisabled:
    def test_connects_without_token(self, client, fresh_store):
        """When auth is off, any client can connect to a campaign WS."""
        with patch("backend.api.websocket.get_settings", return_value=_auth_disabled_settings()), \
             patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            with client.websocket_connect(f"/ws/{_CAMPAIGN_ID}") as ws:
                # Connection accepted — just close cleanly
                pass  # context manager closes on exit


# ---------------------------------------------------------------------------
# ws_campaign — auth enabled
# ---------------------------------------------------------------------------

class TestWsCampaignAuthEnabled:
    def test_rejects_missing_token_with_4001(self, client, fresh_store):
        """Missing token → close code 4001."""
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(f"/ws/{_CAMPAIGN_ID}"):
                    pass
            assert exc_info.value.code == 4001

    def test_rejects_invalid_token_with_4001(self, client, fresh_store):
        """Invalid token → close code 4001."""
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.api.websocket.validate_token", new_callable=AsyncMock, side_effect=Exception("bad token")), \
             patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(f"/ws/{_CAMPAIGN_ID}?token=bad"):
                    pass
            assert exc_info.value.code == 4001

    def test_rejects_non_member_with_4003(self, client, fresh_store):
        """Valid token but user is not a campaign member → close code 4003."""
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.api.websocket.validate_token", new_callable=AsyncMock, return_value=_OUTSIDER), \
             patch("backend.api.websocket.async_session"), \
             patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(f"/ws/{_CAMPAIGN_ID}?token=valid"):
                    pass
            assert exc_info.value.code == 4003

    def test_admin_connects_without_membership(self, client, fresh_store):
        """Admin user can connect to any campaign without being a member."""
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.api.websocket.validate_token", new_callable=AsyncMock, return_value=_ADMIN), \
             patch("backend.api.websocket.async_session"), \
             patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            with client.websocket_connect(f"/ws/{_CAMPAIGN_ID}?token=valid"):
                pass  # Connection accepted

    def test_member_connects_successfully(self, client, fresh_store):
        """Campaign member can connect successfully."""
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.api.websocket.validate_token", new_callable=AsyncMock, return_value=_MEMBER), \
             patch("backend.api.websocket.async_session"), \
             patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            with client.websocket_connect(f"/ws/{_CAMPAIGN_ID}?token=valid"):
                pass  # Connection accepted


# ---------------------------------------------------------------------------
# ws_global — auth disabled (local-dev)
# ---------------------------------------------------------------------------

class TestWsGlobalAuthDisabled:
    def test_connects_without_token(self, client):
        """When auth is off, any client can connect to the global WS."""
        with patch("backend.api.websocket.get_settings", return_value=_auth_disabled_settings()):
            with client.websocket_connect("/ws"):
                pass


# ---------------------------------------------------------------------------
# ws_global — auth enabled
# ---------------------------------------------------------------------------

class TestWsGlobalAuthEnabled:
    def test_rejects_missing_token_with_4001(self, client):
        """Missing token → close code 4001."""
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws"):
                    pass
            assert exc_info.value.code == 4001

    def test_rejects_invalid_token_with_4001(self, client):
        """Invalid token → close code 4001."""
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.api.websocket.validate_token", new_callable=AsyncMock, side_effect=Exception("bad")):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws?token=bad"):
                    pass
            assert exc_info.value.code == 4001

    def test_valid_token_connects_successfully(self, client):
        """Valid token → global WS accepted."""
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.api.websocket.validate_token", new_callable=AsyncMock, return_value=_MEMBER), \
             patch("backend.api.websocket.async_session"):
            with client.websocket_connect("/ws?token=valid"):
                pass


# ---------------------------------------------------------------------------
# ConnectionManager.broadcast — membership filtering
# ---------------------------------------------------------------------------

class TestBroadcastFiltering:
    """Unit tests for ConnectionManager broadcast filtering logic."""

    @pytest.mark.asyncio
    async def test_admin_global_subscriber_receives_all_campaigns(self, fresh_store):
        """Admin connected to global WS receives events for any campaign."""
        from backend.api.websocket import ConnectionManager

        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        mock_ws.send_text = AsyncMock()

        await mgr.connect(mock_ws, "*", user_id=_ADMIN.id, is_admin=True)

        with patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            await mgr.broadcast({"campaign_id": _CAMPAIGN_ID, "event": "test"})

        mock_ws.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_member_global_subscriber_receives_their_campaign(self, fresh_store):
        """Member connected to global WS receives events for campaigns they belong to."""
        from backend.api.websocket import ConnectionManager

        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        mock_ws.send_text = AsyncMock()

        await mgr.connect(mock_ws, "*", user_id=_MEMBER.id, is_admin=False)

        with patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            await mgr.broadcast({"campaign_id": _CAMPAIGN_ID, "event": "test"})

        mock_ws.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_outsider_global_subscriber_filtered_out(self, fresh_store):
        """Non-member connected to global WS does NOT receive campaign events."""
        from backend.api.websocket import ConnectionManager

        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        mock_ws.send_text = AsyncMock()

        await mgr.connect(mock_ws, "*", user_id=_OUTSIDER.id, is_admin=False)

        with patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            await mgr.broadcast({"campaign_id": _CAMPAIGN_ID, "event": "test"})

        mock_ws.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_auth_disabled_global_subscriber_receives_all(self, fresh_store):
        """When auth is disabled (user_id=None), global subscriber receives all events."""
        from backend.api.websocket import ConnectionManager

        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        mock_ws.send_text = AsyncMock()

        await mgr.connect(mock_ws, "*", user_id=None, is_admin=False)

        with patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            await mgr.broadcast({"campaign_id": "any-campaign", "event": "test"})

        mock_ws.send_text.assert_called_once()
