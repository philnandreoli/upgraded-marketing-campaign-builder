"""Router registration for the API application."""

from __future__ import annotations

from fastapi import FastAPI

from backend.api.admin import router as admin_router
from backend.api.budget_entries import router as budget_entries_router
from backend.api.experiment_insights import router as experiment_insights_router
from backend.api.experiments import global_router as experiments_global_router, router as experiments_router
from backend.api.campaigns import me_router, router as campaigns_router
from backend.api.personas import router as personas_router
from backend.api.campaign_assets import router as campaign_assets_router
from backend.api.campaign_comments import router as campaign_comments_router
from backend.api.content_chat import router as content_chat_router
from backend.api.campaign_clone import router as campaign_clone_router
from backend.api.campaign_members import router as campaign_members_router
from backend.api.campaign_schedule import router as campaign_schedule_router
from backend.api.campaign_workflow import router as campaign_workflow_router
from backend.api.templates import router as templates_router
from backend.api.websocket import router as ws_router, ticket_router as ws_ticket_router
from backend.api.workspace_members import router as workspace_members_router
from backend.api.workspaces import router as workspaces_router


def register_routers(app: FastAPI) -> None:
    """Register all API routers on *app*."""
    app.include_router(admin_router)
    app.include_router(me_router, prefix="/api")
    app.include_router(campaigns_router, prefix="/api/workspaces/{workspace_id}")
    app.include_router(campaign_assets_router, prefix="/api/workspaces/{workspace_id}")
    app.include_router(campaign_schedule_router, prefix="/api/workspaces/{workspace_id}")
    app.include_router(campaign_workflow_router, prefix="/api/workspaces/{workspace_id}")
    app.include_router(campaign_comments_router, prefix="/api/workspaces/{workspace_id}")
    app.include_router(content_chat_router, prefix="/api/workspaces/{workspace_id}")
    app.include_router(campaign_clone_router, prefix="/api/workspaces/{workspace_id}")
    app.include_router(budget_entries_router, prefix="/api/workspaces/{workspace_id}")
    app.include_router(experiments_router, prefix="/api/workspaces/{workspace_id}")
    app.include_router(experiment_insights_router, prefix="/api/workspaces/{workspace_id}")
    app.include_router(campaign_members_router, prefix="/api/workspaces/{workspace_id}")
    app.include_router(personas_router, prefix="/api/workspaces/{workspace_id}")
    app.include_router(templates_router, prefix="/api")
    app.include_router(workspaces_router, prefix="/api")
    app.include_router(workspace_members_router, prefix="/api")
    app.include_router(experiments_global_router, prefix="/api")
    app.include_router(ws_router, prefix="/ws")
    app.include_router(ws_ticket_router, prefix="/api/ws")
