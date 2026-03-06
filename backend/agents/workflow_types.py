"""
Foundational types for the declarative agent pipeline.

``WorkflowAction``      — enum of possible stage outcomes
``StageExecutionResult`` — Pydantic model returned by every stage handler
``StageDefinition``     — dataclass describing a pipeline stage
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from backend.models.campaign import Campaign, CampaignStatus


class WorkflowAction(str, Enum):
    """Outcome returned by a pipeline stage."""

    CONTINUE = "continue"
    WAIT = "wait"
    COMPLETE = "complete"
    FAIL = "fail"


class StageExecutionResult(BaseModel):
    """Result produced by a single pipeline stage handler."""

    action: WorkflowAction
    campaign: Campaign
    next_stage: str | None = None
    reason: str | None = None


@dataclass
class StageDefinition:
    """Describes a single stage in the agent pipeline."""

    name: str
    status: CampaignStatus
    handler: Callable[[Campaign, dict[str, Any]], Awaitable[Campaign]]
    condition: Callable[[Campaign], bool] = field(default=lambda c: True)
    terminal_on_failure: bool = True
