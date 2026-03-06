"""
Workflow checkpoint models — represent the durable state of a coordinator pipeline run.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class WorkflowWaitType(str, Enum):
    """Describes what kind of human input the workflow is waiting for."""

    CLARIFICATION = "clarification"
    CONTENT_APPROVAL = "content_approval"


class WorkflowCheckpoint(BaseModel):
    """Durable snapshot of a coordinator workflow's progress.

    One row per campaign; upserted whenever the coordinator advances a
    stage or begins waiting for human input.
    """

    campaign_id: str
    current_stage: str
    wait_type: Optional[WorkflowWaitType] = None
    revision_cycle: int = 0
    resume_token: Optional[str] = None
    context: dict[str, Any] = Field(default_factory=dict)
    wait_started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
