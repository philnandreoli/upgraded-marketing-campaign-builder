"""
Typed event models for the campaign pipeline.

These models define the schema for events emitted by the CoordinatorAgent.
They are serialised to ``dict`` before being passed to the event callback so
the existing callback contract is preserved; event payloads are a strict
superset of the untyped dicts that were emitted previously.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowEvent(BaseModel):
    """Base class for all pipeline events."""

    event_type: str
    campaign_id: str
    timestamp: datetime = Field(default_factory=_utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)
    version: str = "1.0"


class StageStartedEvent(WorkflowEvent):
    """Emitted when a pipeline stage begins."""

    event_type: str = "stage_started"
    stage: str


class StageCompletedEvent(WorkflowEvent):
    """Emitted when a pipeline stage finishes successfully."""

    event_type: str = "stage_completed"
    stage: str
    output: dict[str, Any] = Field(default_factory=dict)


class StageErrorEvent(WorkflowEvent):
    """Emitted when a pipeline stage fails."""

    event_type: str = "stage_error"
    stage: str
    error: str


class ClarificationRequestedEvent(WorkflowEvent):
    """Emitted when the pipeline needs additional input from the user."""

    event_type: str = "clarification_requested"
    questions: list[dict[str, Any]]
    context_summary: str = ""


class ContentApprovalRequestedEvent(WorkflowEvent):
    """Emitted when content is ready for human per-piece approval."""

    event_type: str = "content_approval_requested"
    content: dict[str, Any] = Field(default_factory=dict)
    revision_cycle: int = 0
