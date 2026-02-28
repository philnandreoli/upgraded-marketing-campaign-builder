"""
WebSocket endpoint for real-time pipeline updates.

Clients connect to  ws://host/ws/{campaign_id}  (or /ws for all campaigns)
and receive JSON messages as each pipeline stage starts / completes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self) -> None:
        # campaign_id -> list of connected sockets  ("*" = global subscribers)
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, campaign_id: str = "*") -> None:
        await websocket.accept()
        self._connections.setdefault(campaign_id, []).append(websocket)
        logger.info("WS connected: campaign=%s (total=%d)", campaign_id, self._total())

    def disconnect(self, websocket: WebSocket, campaign_id: str = "*") -> None:
        conns = self._connections.get(campaign_id, [])
        if websocket in conns:
            conns.remove(websocket)
        logger.info("WS disconnected: campaign=%s (total=%d)", campaign_id, self._total())

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a message to all global subscribers and to subscribers of
        the specific campaign_id (if present in the message)."""
        payload = json.dumps(message, default=str)

        targets: list[WebSocket] = list(self._connections.get("*", []))
        cid = message.get("campaign_id")
        if cid and cid in self._connections:
            targets.extend(self._connections[cid])

        stale: list[tuple[str, WebSocket]] = []
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                # Connection probably closed — mark for cleanup
                stale.append((cid or "*", ws))

        for key, ws in stale:
            self.disconnect(ws, key)

    def _total(self) -> int:
        return sum(len(v) for v in self._connections.values())


# Module-level singleton so the campaigns router can import it
manager = ConnectionManager()


# ---------------------------------------------------------------------------
# WebSocket routes
# ---------------------------------------------------------------------------

@router.websocket("")
async def ws_global(websocket: WebSocket) -> None:
    """Subscribe to events for ALL campaigns."""
    await manager.connect(websocket, "*")
    try:
        while True:
            # Keep the connection alive; we don't expect inbound messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, "*")


@router.websocket("/{campaign_id}")
async def ws_campaign(websocket: WebSocket, campaign_id: str) -> None:
    """Subscribe to events for a specific campaign."""
    await manager.connect(websocket, campaign_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, campaign_id)
