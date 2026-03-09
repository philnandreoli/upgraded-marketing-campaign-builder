"""
WebSocket endpoint for real-time pipeline updates.

Clients connect to  ws://host/ws/{campaign_id}  (or /ws for all campaigns)
and receive JSON messages as each pipeline stage starts / completes.

When AUTH_ENABLED=True, a ``token`` query parameter is required:
  ws://host/ws/{campaign_id}?token=<jwt>

The connection is rejected with close code 4001 (Unauthorized) if the token
is missing or invalid, and with 4003 (Forbidden) if the user does not have
READ access to the requested campaign.

Security characteristics of the query-string token model
---------------------------------------------------------
Passing the bearer token as a query parameter is the only mechanism
available at the browser WebSocket API boundary — the ``WebSocket``
constructor does not support custom request headers.  The implications are:

* **Nginx access logs**: By default nginx logs the full request URI,
  including the query string.  The ``/ws`` location in ``nginx.conf``
  sets ``access_log off`` to prevent tokens from being recorded.  Any
  additional reverse-proxy or ingress layer in front of nginx must be
  configured equivalently (e.g. Azure Application Gateway path rules,
  Container App ingress log settings).

* **Browser history / referrer**: The WebSocket URL is not stored in
  browser history, and the ``Referer`` header is not sent for WebSocket
  upgrades, so token leakage via those vectors is not a concern.

* **TLS**: All production traffic must use ``wss://`` (TLS) so the token
  is encrypted in transit.

Follow-up (TODO): Replace query-string tokens with a short-lived,
single-use ticket issued by a ``POST /ws/ticket`` endpoint.  The client
exchanges a full bearer token for a ticket (opaque, short TTL, stored
server-side) and then passes ``?ticket=<value>`` to the WebSocket
upgrade.  This limits exposure because the ticket has no value outside
the single upgrade request.  See issue #07 for details.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.config import get_settings
from backend.models.user import User, UserRole
from backend.infrastructure.auth import validate_token
from backend.infrastructure.campaign_store import get_campaign_store
from backend.infrastructure.database import async_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

# WebSocket close codes (application-defined range 4000-4999)
_WS_UNAUTHORIZED = 4001
_WS_FORBIDDEN = 4003


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self) -> None:
        # campaign_id -> list of connected sockets  ("*" = global subscribers)
        self._connections: dict[str, list[WebSocket]] = {}
        # WebSocket -> (user_id | None, is_admin)
        # user_id is None when auth is disabled (local-dev mode).
        self._ws_meta: dict[WebSocket, tuple[Optional[str], bool]] = {}

    async def connect(
        self,
        websocket: WebSocket,
        campaign_id: str = "*",
        user_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> None:
        await websocket.accept()
        self._connections.setdefault(campaign_id, []).append(websocket)
        self._ws_meta[websocket] = (user_id, is_admin)
        logger.info("WS connected: campaign=%s (total=%d)", campaign_id, self._total())

    def disconnect(self, websocket: WebSocket, campaign_id: str = "*") -> None:
        conns = self._connections.get(campaign_id, [])
        if websocket in conns:
            conns.remove(websocket)
        self._ws_meta.pop(websocket, None)
        logger.info("WS disconnected: campaign=%s (total=%d)", campaign_id, self._total())

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a message to all authorized subscribers.

        Campaign-specific subscribers are already access-checked on connect.
        Global (``"*"``) subscribers are filtered here: admins receive all
        events; other authenticated users receive only events for campaigns
        they are a member of; unauthenticated connections (auth disabled)
        receive all events.
        """
        payload = json.dumps(message, default=str)
        cid = message.get("campaign_id")

        # (bucket_key, websocket) pairs to send to
        targets: list[tuple[str, WebSocket]] = []

        # Campaign-specific subscribers — already auth-checked on connect
        if cid and cid in self._connections:
            for ws in list(self._connections[cid]):
                targets.append((cid, ws))

        # Global subscribers — filter by campaign membership
        for ws in list(self._connections.get("*", [])):
            user_id, is_admin = self._ws_meta.get(ws, (None, False))
            if user_id is None:
                # Auth disabled (local-dev) — no filtering
                targets.append(("*", ws))
            elif is_admin:
                targets.append(("*", ws))
            elif cid:
                store = get_campaign_store()
                role = await store.get_member_role(cid, user_id)
                if role is not None:
                    targets.append(("*", ws))
            else:
                # Message has no campaign_id — treated as a system-level broadcast
                # (not campaign-specific), safe to send to all authenticated users.
                targets.append(("*", ws))

        stale: list[tuple[str, WebSocket]] = []
        for bucket, ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                # Connection probably closed — mark for cleanup
                stale.append((bucket, ws))

        for key, ws in stale:
            self.disconnect(ws, key)

    def _total(self) -> int:
        return sum(len(v) for v in self._connections.values())


# Module-level singleton so the campaigns router can import it
manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _authenticate_ws(token: Optional[str]) -> Optional[User]:
    """Validate the WS token query param when auth is enabled.

    Returns the authenticated User, or None when auth is disabled.
    Raises an Exception (HTTPException) on invalid/missing token.
    """
    settings = get_settings()
    if not settings.oidc.enabled:
        return None
    if not token:
        raise ValueError("Token required")
    async with async_session() as db:
        return await validate_token(token, db)


# ---------------------------------------------------------------------------
# WebSocket routes
# ---------------------------------------------------------------------------

@router.websocket("")
async def ws_global(websocket: WebSocket, token: Optional[str] = None) -> None:
    """Subscribe to events for ALL campaigns (Dashboard).

    Requires a valid JWT ``token`` query parameter when AUTH_ENABLED=True.
    Admins receive all events; other users receive only events for campaigns
    they are a member of.
    """
    try:
        user = await _authenticate_ws(token)
    except Exception:
        await websocket.close(code=_WS_UNAUTHORIZED)
        return

    user_id = user.id if user else None
    is_admin = user.is_admin if user else False

    await manager.connect(websocket, "*", user_id=user_id, is_admin=is_admin)
    try:
        while True:
            # Keep the connection alive; we don't expect inbound messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, "*")


@router.websocket("/{campaign_id}")
async def ws_campaign(
    websocket: WebSocket, campaign_id: str, token: Optional[str] = None
) -> None:
    """Subscribe to events for a specific campaign.

    Requires a valid JWT ``token`` query parameter when AUTH_ENABLED=True.
    The user must be a member of the campaign (or an admin), otherwise the
    connection is rejected with close code 4003 (Forbidden).
    """
    try:
        user = await _authenticate_ws(token)
    except Exception:
        await websocket.close(code=_WS_UNAUTHORIZED)
        return

    if user is not None and not user.is_admin:
        store = get_campaign_store()
        role = await store.get_member_role(campaign_id, user.id)
        if role is None:
            await websocket.close(code=_WS_FORBIDDEN)
            return

    user_id = user.id if user else None
    is_admin = user.is_admin if user else False

    await manager.connect(websocket, campaign_id, user_id=user_id, is_admin=is_admin)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, campaign_id)
