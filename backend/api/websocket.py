"""
WebSocket endpoint for real-time pipeline updates.

Clients connect to  ws://host/ws/{campaign_id}  (or /ws for all campaigns)
and receive JSON messages as each pipeline stage starts / completes.

Authentication uses a short-lived, single-use opaque ticket:

  1. Client calls ``POST /api/ws/ticket`` (Bearer auth) to obtain a ticket.
  2. Client connects using ``?ticket=<opaque>`` instead of the raw JWT.
  3. Server validates and consumes the ticket on upgrade, then discards it.

The ticket is valid for 30 seconds and is single-use.  The connection is
rejected with close code 4001 (Unauthorized) if the ticket is missing,
expired, or has already been consumed, and with 4003 (Forbidden) if the
user does not have READ access to the requested campaign.

This approach mitigates the OWASP A07:2021 risk of JWT leakage through
reverse-proxy / CDN access logs, since the opaque ticket has no value
outside the single WebSocket upgrade request.
"""

import asyncio
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request, Response, WebSocket, WebSocketDisconnect

from backend.config import get_settings
from backend.core.rate_limit import limiter
from backend.infrastructure.auth import require_authenticated
from backend.infrastructure.campaign_store import get_campaign_store
from backend.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])
ticket_router = APIRouter(tags=["websocket"])

# WebSocket close codes (application-defined range 4000-4999)
_WS_UNAUTHORIZED = 4001
_WS_FORBIDDEN = 4003

# Ticket time-to-live (seconds)
_TICKET_TTL_SECONDS = 30

# In-memory single-use ticket store: ticket → {"user_id": str, "expires_at": datetime}
# Tickets are popped (consumed) on first use. A background cleanup loop evicts
# any tickets that were created but never redeemed.
_ws_tickets: dict[str, dict] = {}


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
# Ticket endpoint (HTTP REST — registered under /api/ws prefix)
# ---------------------------------------------------------------------------

@ticket_router.post("/ticket")
@limiter.limit("10/minute")
async def create_ws_ticket(request: Request, response: Response, user: User = Depends(require_authenticated)) -> dict:
    """Issue a short-lived, single-use ticket for WebSocket authentication.

    The ticket is valid for 30 seconds and can only be used once.
    Exchange it for a WebSocket connection via ``?ticket=<value>``.

    Requires a valid Bearer token in the ``Authorization`` header.
    """
    ticket = secrets.token_urlsafe(32)
    _ws_tickets[ticket] = {
        "user_id": user.id,
        "expires_at": datetime.utcnow() + timedelta(seconds=_TICKET_TTL_SECONDS),
    }
    return {"ticket": ticket}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _authenticate_ws_ticket(ticket: Optional[str]) -> Optional[User]:
    """Validate and consume a single-use WS ticket.

    Returns the authenticated User, or None when auth is disabled.
    Raises ValueError on a missing, expired, or already-consumed ticket.
    """
    settings = get_settings()
    if not settings.oidc.enabled:
        return None  # Auth disabled — local-dev / testing mode
    if not ticket:
        raise ValueError("Ticket required")
    entry = _ws_tickets.pop(ticket, None)  # single-use: pop immediately
    if not entry or entry["expires_at"] < datetime.utcnow():
        raise ValueError("Invalid or expired ticket")
    store = get_campaign_store()
    user = await store.get_user(entry["user_id"])
    if user is None:
        raise ValueError("User not found")
    if not user.is_active:
        raise ValueError("Account deactivated")
    return user


async def _ticket_cleanup_loop() -> None:
    """Background task: evict unredeemed expired tickets every 60 seconds."""
    while True:
        await asyncio.sleep(60)
        now = datetime.utcnow()
        expired = [k for k, v in list(_ws_tickets.items()) if v["expires_at"] < now]
        for k in expired:
            _ws_tickets.pop(k, None)
        if expired:
            logger.debug("WS ticket cleanup: removed %d expired tickets", len(expired))


def start_ticket_cleanup_task() -> None:
    """Schedule the background ticket-cleanup loop on the running event loop."""
    asyncio.ensure_future(_ticket_cleanup_loop())


# ---------------------------------------------------------------------------
# WebSocket routes
# ---------------------------------------------------------------------------

@router.websocket("")
async def ws_global(websocket: WebSocket, ticket: Optional[str] = None) -> None:
    """Subscribe to events for ALL campaigns (Dashboard).

    Requires a valid ``ticket`` query parameter when AUTH_ENABLED=True.
    Obtain a ticket from ``POST /api/ws/ticket`` before connecting.
    Admins receive all events; other users receive only events for campaigns
    they are a member of.
    """
    try:
        user = await _authenticate_ws_ticket(ticket)
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
    websocket: WebSocket, campaign_id: str, ticket: Optional[str] = None
) -> None:
    """Subscribe to events for a specific campaign.

    Requires a valid ``ticket`` query parameter when AUTH_ENABLED=True.
    Obtain a ticket from ``POST /api/ws/ticket`` before connecting.
    The user must be a member of the campaign (or an admin), otherwise the
    connection is rejected with close code 4003 (Forbidden).
    """
    try:
        user = await _authenticate_ws_ticket(ticket)
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
