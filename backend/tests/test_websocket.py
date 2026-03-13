"""
Tests for WebSocket authentication and authorization.

Validates that:
- Connections succeed when auth is disabled (local-dev)
- Connections are rejected with 4001 when a ticket is missing/invalid (auth enabled)
- Expired and already-consumed tickets are rejected with 4001
- Connections to campaign-specific WS are rejected with 4003 when the user is
  not a member of that campaign
- Admins can connect to any campaign without membership
- Campaign members can connect
- Global broadcast filters events by campaign membership for non-admin users
- POST /api/ws/ticket issues valid tickets (requires Bearer auth)
"""

from __future__ import annotations

from datetime import datetime, timedelta
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
    with patch("backend.apps.api.startup.init_db", new_callable=AsyncMock), \
         patch("backend.apps.api.startup.close_db", new_callable=AsyncMock), \
         patch("backend.api.websocket.start_ticket_cleanup_task"):
        yield


@pytest.fixture(autouse=True)
def _clear_ws_tickets():
    """Ensure the in-memory ticket store is empty before and after each test."""
    from backend.api.websocket import _ws_tickets
    _ws_tickets.clear()
    yield
    _ws_tickets.clear()


@pytest.fixture
def fresh_store():
    store = InMemoryCampaignStore()
    store._members[(_CAMPAIGN_ID, _MEMBER.id)] = CampaignMemberRole.VIEWER.value
    store._users[_MEMBER.id] = _MEMBER
    store._users[_ADMIN.id] = _ADMIN
    store._users[_OUTSIDER.id] = _OUTSIDER
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


def _make_ticket(user: User, *, expired: bool = False) -> str:
    """Insert a ticket for *user* into the module-level store and return it."""
    from backend.api.websocket import _ws_tickets
    import secrets as _secrets
    ticket = _secrets.token_urlsafe(16)
    if expired:
        expires_at = datetime.utcnow() - timedelta(seconds=1)
    else:
        expires_at = datetime.utcnow() + timedelta(seconds=30)
    _ws_tickets[ticket] = {"user_id": user.id, "expires_at": expires_at}
    return ticket


# ---------------------------------------------------------------------------
# ws_campaign — auth disabled (local-dev)
# ---------------------------------------------------------------------------

class TestWsCampaignAuthDisabled:
    def test_connects_without_ticket(self, client, fresh_store):
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
    def test_rejects_missing_ticket_with_4001(self, client, fresh_store):
        """Missing ticket → close code 4001."""
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(f"/ws/{_CAMPAIGN_ID}"):
                    pass
            assert exc_info.value.code == 4001

    def test_rejects_invalid_ticket_with_4001(self, client, fresh_store):
        """Unknown (never-issued) ticket → close code 4001."""
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(f"/ws/{_CAMPAIGN_ID}?ticket=bogus"):
                    pass
            assert exc_info.value.code == 4001

    def test_rejects_expired_ticket_with_4001(self, client, fresh_store):
        """Expired ticket → close code 4001."""
        ticket = _make_ticket(_MEMBER, expired=True)
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(f"/ws/{_CAMPAIGN_ID}?ticket={ticket}"):
                    pass
            assert exc_info.value.code == 4001

    def test_rejects_reused_ticket_with_4001(self, client, fresh_store):
        """Ticket consumed on first use → second connection rejected with 4001."""
        ticket = _make_ticket(_MEMBER)
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            # First use succeeds
            with client.websocket_connect(f"/ws/{_CAMPAIGN_ID}?ticket={ticket}"):
                pass
            # Second use is rejected because the ticket was popped on first use
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(f"/ws/{_CAMPAIGN_ID}?ticket={ticket}"):
                    pass
            assert exc_info.value.code == 4001

    def test_rejects_non_member_with_4003(self, client, fresh_store):
        """Valid ticket but user is not a campaign member → close code 4003."""
        ticket = _make_ticket(_OUTSIDER)
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(f"/ws/{_CAMPAIGN_ID}?ticket={ticket}"):
                    pass
            assert exc_info.value.code == 4003

    def test_admin_connects_without_membership(self, client, fresh_store):
        """Admin user can connect to any campaign without being a member."""
        ticket = _make_ticket(_ADMIN)
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            with client.websocket_connect(f"/ws/{_CAMPAIGN_ID}?ticket={ticket}"):
                pass  # Connection accepted

    def test_member_connects_successfully(self, client, fresh_store):
        """Campaign member can connect successfully."""
        ticket = _make_ticket(_MEMBER)
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            with client.websocket_connect(f"/ws/{_CAMPAIGN_ID}?ticket={ticket}"):
                pass  # Connection accepted


# ---------------------------------------------------------------------------
# ws_global — auth disabled (local-dev)
# ---------------------------------------------------------------------------

class TestWsGlobalAuthDisabled:
    def test_connects_without_ticket(self, client):
        """When auth is off, any client can connect to the global WS."""
        with patch("backend.api.websocket.get_settings", return_value=_auth_disabled_settings()):
            with client.websocket_connect("/ws"):
                pass


# ---------------------------------------------------------------------------
# ws_global — auth enabled
# ---------------------------------------------------------------------------

class TestWsGlobalAuthEnabled:
    def test_rejects_missing_ticket_with_4001(self, client):
        """Missing ticket → close code 4001."""
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws"):
                    pass
            assert exc_info.value.code == 4001

    def test_rejects_invalid_ticket_with_4001(self, client, fresh_store):
        """Unknown (never-issued) ticket → close code 4001."""
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws?ticket=bogus"):
                    pass
            assert exc_info.value.code == 4001

    def test_valid_ticket_connects_successfully(self, client, fresh_store):
        """Valid ticket → global WS accepted."""
        ticket = _make_ticket(_MEMBER)
        with patch("backend.api.websocket.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.api.websocket.get_campaign_store", return_value=fresh_store):
            with client.websocket_connect(f"/ws?ticket={ticket}"):
                pass


# ---------------------------------------------------------------------------
# POST /api/ws/ticket — ticket issuance endpoint
# ---------------------------------------------------------------------------

class TestWsTicketEndpoint:
    def test_returns_ticket_for_authenticated_user(self, client):
        """Authenticated user receives a ticket string."""
        from backend.infrastructure.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: _MEMBER
        try:
            r = client.post("/api/ws/ticket")
            assert r.status_code == 200
            body = r.json()
            assert "ticket" in body
            assert isinstance(body["ticket"], str)
            assert len(body["ticket"]) > 0
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_ticket_stored_in_memory_with_user_id(self, client):
        """Created ticket is stored in _ws_tickets with the correct user_id."""
        from backend.api.websocket import _ws_tickets
        from backend.infrastructure.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: _MEMBER
        try:
            r = client.post("/api/ws/ticket")
            ticket = r.json()["ticket"]
            assert ticket in _ws_tickets
            assert _ws_tickets[ticket]["user_id"] == _MEMBER.id
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_returns_401_when_auth_disabled(self, client):
        """When auth is disabled (user=None), the endpoint returns 401."""
        from backend.infrastructure.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: None
        try:
            r = client.post("/api/ws/ticket")
            assert r.status_code == 401
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_returns_401_without_auth_header(self, client):
        """No Authorization header and auth enabled → 401."""
        with patch("backend.infrastructure.auth.get_settings", return_value=_auth_enabled_settings()), \
             patch("backend.infrastructure.database.get_db", new_callable=AsyncMock):
            r = client.post("/api/ws/ticket")
        assert r.status_code == 401


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
