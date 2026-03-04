"""
FastAPI application entry-point.

Run with:
    uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.services.tracing import setup_tracing
from backend.services.agent_registry import register_agents

# ------------------------------------------------------------------
# Tracing — must be initialised before any LLM client is created
# ------------------------------------------------------------------
setup_tracing()

# ------------------------------------------------------------------
# Foundry Agent Operations — register agents (idempotent / reuse)
# ------------------------------------------------------------------
register_agents()

# ------------------------------------------------------------------
# App factory
# ------------------------------------------------------------------

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.app.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

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


# ------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "0.1.0"}


# ------------------------------------------------------------------
# Database lifecycle
# ------------------------------------------------------------------
from backend.services.database import init_db, close_db

@app.on_event("startup")
async def on_startup():
    await init_db()

@app.on_event("shutdown")
async def on_shutdown():
    await close_db()


# ------------------------------------------------------------------
# API routers
# ------------------------------------------------------------------
from backend.api.admin import router as admin_router
from backend.api.campaigns import router as campaigns_router
from backend.api.websocket import router as ws_router

app.include_router(admin_router)
app.include_router(campaigns_router, prefix="/api")
app.include_router(ws_router, prefix="/ws")
