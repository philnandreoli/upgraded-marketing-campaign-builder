"""FastAPI application entry-point for the API app boundary.

Run with:
    uvicorn backend.apps.api.main:app --reload --port 8000

This module owns only HTTP / WebSocket concerns:
- Logging configuration
- Distributed tracing bootstrap
- CORS middleware
- Health check endpoints
- Database and event-subscriber lifecycle
- Router registration

Workflow-engine agent registration is intentionally **not** performed here;
it is the responsibility of the worker/orchestration process.
"""

from __future__ import annotations

import logging

import sqlalchemy
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.core.tracing import setup_tracing

# ------------------------------------------------------------------
# Logging — must be configured first so all subsequent log calls
# (including setup_tracing) use the right format.
# force=True is required because uvicorn configures the root logger
# via dictConfig before importing the app module, which causes
# basicConfig() to silently no-op without it.
# ------------------------------------------------------------------

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.app.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    force=True,
)

# ------------------------------------------------------------------
# Tracing — must be initialised before any LLM client is created
# ------------------------------------------------------------------
setup_tracing()

app = FastAPI(
    title="Marketing Campaign Builder",
    description="AI-powered multi-agent system for building marketing campaigns",
    version="0.1.0",
)

# CORS — restrict cross-origin access to configured origins.
# In development the default ["*"] is permissive for convenience.
# Set CORS_ALLOWED_ORIGINS in production to an explicit list of frontend
# origins, e.g. '["https://app.example.com"]'.
# When the frontend is served by the same nginx reverse-proxy that proxies
# API traffic (the default production topology), CORS is not exercised by
# the browser, so this setting mainly guards direct API access from other
# origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Health checks
# ------------------------------------------------------------------

@app.get("/health/live")
async def health_live():
    """Liveness probe — process is running."""
    return {"status": "alive"}


@app.get("/health/ready")
async def health_ready():
    """Readiness probe — dependencies (DB + executor) are reachable."""
    from backend.infrastructure.database import engine  # noqa: PLC0415
    from backend.infrastructure.workflow_executor import get_executor  # noqa: PLC0415

    # Check DB connectivity
    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB health check failed: %s", exc)

    # Check executor health
    executor_ok = False
    try:
        executor_ok = await get_executor().health_check()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Executor health check failed: %s", exc)

    checks = {"database": db_ok, "executor": executor_ok}
    if db_ok and executor_ok:
        return {"status": "ready", "checks": checks}

    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "checks": checks},
    )


@app.get("/health")
async def health_check():
    """Backward-compatible alias for /health/live."""
    return {"status": "alive"}


# ------------------------------------------------------------------
# Database and event-subscriber lifecycle (API-specific)
# ------------------------------------------------------------------
from backend.apps.api.startup import make_shutdown_handler, make_startup_handler  # noqa: E402

app.add_event_handler("startup", make_startup_handler(app))
app.add_event_handler("shutdown", make_shutdown_handler(app))

# ------------------------------------------------------------------
# API routers
# ------------------------------------------------------------------
from backend.apps.api.routers import register_routers  # noqa: E402

register_routers(app)
