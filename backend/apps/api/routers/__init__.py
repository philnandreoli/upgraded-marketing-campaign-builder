"""Router registration for the API application."""

from __future__ import annotations

from fastapi import FastAPI

from backend.api.admin import router as admin_router
from backend.api.campaigns import router as campaigns_router
from backend.api.campaign_members import router as campaign_members_router
from backend.api.campaign_workflow import router as campaign_workflow_router
from backend.api.websocket import router as ws_router
from backend.api.workspace_members import router as workspace_members_router
from backend.api.workspaces import router as workspaces_router


def register_routers(app: FastAPI) -> None:
    """Register all API routers on *app*."""
    app.include_router(admin_router)
    app.include_router(campaigns_router, prefix="/api")
    app.include_router(campaign_workflow_router, prefix="/api")
    app.include_router(campaign_members_router, prefix="/api")
    app.include_router(workspaces_router, prefix="/api")
    app.include_router(workspace_members_router, prefix="/api")
    app.include_router(ws_router, prefix="/ws")
