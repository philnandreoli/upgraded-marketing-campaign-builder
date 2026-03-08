"""Compatibility shim — database has moved to backend.infrastructure.database."""
from backend.infrastructure.database import *  # noqa: F401, F403
from backend.infrastructure.database import (  # noqa: F401
    Base, CampaignMemberRow, CampaignRow, DATABASE_URL, EventOverflowRow,
    UserRow, WorkflowCheckpointRow, WorkflowSignalRow, WorkspaceMemberRow,
    WorkspaceRow, async_session, close_db, engine, get_db, init_db,
)
