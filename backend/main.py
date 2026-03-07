"""
FastAPI application entry-point.

Run with:
    uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import logging

import sqlalchemy
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.services.tracing import setup_tracing
from backend.services.agent_registry import register_agents

# ------------------------------------------------------------------
# Logging — must be configured first so all subsequent log calls
# (including setup_tracing / register_agents) use the right format.
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

# ------------------------------------------------------------------
# Foundry Agent Operations — register agents (idempotent / reuse)
# ------------------------------------------------------------------
register_agents()

app = FastAPI(
    title="Marketing Campaign Builder",
    description="AI-powered multi-agent system for building marketing campaigns",
    version="0.1.0",
)

# CORS — allow the React frontend during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
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
    from backend.services.database import engine  # noqa: PLC0415
    from backend.services.workflow_executor import get_executor  # noqa: PLC0415

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
# Database lifecycle
# ------------------------------------------------------------------
from backend.services.database import init_db, close_db

@app.on_event("startup")
async def on_startup():
    await init_db()
    # Start the cross-process event subscriber when the pipeline is running
    # in an external worker process.  In in-process mode events flow directly
    # via InProcessEventPublisher without touching Postgres LISTEN/NOTIFY.
    if settings.app.workflow_executor != "in_process":
        from backend.api.websocket import manager as ws_manager  # noqa: PLC0415
        from backend.services.database import DATABASE_URL  # noqa: PLC0415
        from backend.services.event_subscriber import EventSubscriber  # noqa: PLC0415

        dsn = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        subscriber = EventSubscriber(
            dsn=dsn,
            ws_manager=ws_manager,
            channel_name=settings.events.channel_name,
        )
        subscriber.start()
        app.state.event_subscriber = subscriber

@app.on_event("shutdown")
async def on_shutdown():
    subscriber = getattr(app.state, "event_subscriber", None)
    if subscriber is not None:
        await subscriber.stop()
    await close_db()


# ------------------------------------------------------------------
# API routers
# ------------------------------------------------------------------
from backend.api.admin import router as admin_router
from backend.api.campaigns import router as campaigns_router
from backend.api.campaign_workflow import router as campaign_workflow_router
from backend.api.campaign_members import router as campaign_members_router
from backend.api.websocket import router as ws_router

app.include_router(admin_router)
app.include_router(campaigns_router, prefix="/api")
app.include_router(campaign_workflow_router, prefix="/api")
app.include_router(campaign_members_router, prefix="/api")
app.include_router(ws_router, prefix="/ws")
