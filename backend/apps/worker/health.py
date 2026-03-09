"""
Health HTTP server for the workflow-engine worker.

Exposes two endpoints on a dedicated TCP port:

- ``GET /health/live``  — process is running.
- ``GET /health/ready`` — DB reachable, schema compatible, and queue receiver active.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

import sqlalchemy
from aiohttp import web

logger = logging.getLogger(__name__)


class HealthServer:
    """Lightweight aiohttp server that exposes worker health endpoints.

    Parameters
    ----------
    port:
        TCP port to listen on.
    shutdown_event:
        Shared :class:`asyncio.Event` that signals the worker is shutting
        down.  The server cleans itself up once the event is set.
    get_receiver_active:
        Zero-argument callable that returns ``True`` when the queue receiver
        loop is running.
    get_sb_client:
        Zero-argument callable that returns the live ``ServiceBusClient``, or
        ``None`` before the connection is established.
    """

    def __init__(
        self,
        *,
        port: int,
        shutdown_event: asyncio.Event,
        get_receiver_active: Callable[[], bool],
        get_sb_client: Callable[[], Any],
    ) -> None:
        self._port = port
        self._shutdown_event = shutdown_event
        self._get_receiver_active = get_receiver_active
        self._get_sb_client = get_sb_client

    async def run(self) -> None:
        """Start the health HTTP server and block until shutdown is requested."""
        app = web.Application()
        app.router.add_get("/health/live", self._handle_health_live)
        app.router.add_get("/health/ready", self._handle_health_ready)

        runner = web.AppRunner(app)
        await runner.setup()
        # Bind to all interfaces so container orchestrators (Kubernetes,
        # Azure Container Apps) can reach the health endpoints from outside
        # the container network namespace.
        site = web.TCPSite(runner, "0.0.0.0", self._port)
        await site.start()
        logger.info("Health server listening on port %d", self._port)

        try:
            await self._shutdown_event.wait()
        finally:
            await runner.cleanup()

    async def _handle_health_live(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "alive"})

    async def _handle_health_ready(self, _request: web.Request) -> web.Response:
        db_ok = await self._check_db_health()
        schema_ok = await self._check_schema_health()
        receiver_ok = self._get_receiver_active() and self._get_sb_client() is not None

        checks = {"db": db_ok, "schema": schema_ok, "receiver": receiver_ok}
        if db_ok and schema_ok and receiver_ok:
            return web.json_response({"status": "ready", **checks})

        return web.json_response(
            {"status": "not_ready", **checks},
            status=503,
        )

    async def _check_db_health(self) -> bool:
        """Return ``True`` when the database is reachable."""
        try:
            from backend.infrastructure.database import engine  # noqa: PLC0415

            async with engine.connect() as conn:
                await conn.execute(sqlalchemy.text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning("DB health check failed: %s", exc)
            return False

    async def _check_schema_health(self) -> bool:
        """Return ``True`` when the database schema is at the expected Alembic head."""
        try:
            from backend.infrastructure.database import check_schema_compatibility  # noqa: PLC0415

            await check_schema_compatibility()
            return True
        except Exception as exc:
            logger.warning("Schema compatibility check failed: %s", exc)
            return False
