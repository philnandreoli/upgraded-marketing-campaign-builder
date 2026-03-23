"""
Agent message models — represent the messages flowing between agents.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Who authored a message."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    AGENT = "agent"
    HUMAN_REVIEWER = "human_reviewer"


class AgentType(str, Enum):
    """Identifiers for each agent in the system."""

    COORDINATOR = "coordinator"
    STRATEGY = "strategy"
    CONTENT_CREATOR = "content_creator"
    CHANNEL_PLANNER = "channel_planner"
    ANALYTICS = "analytics"
    REVIEW_QA = "review_qa"
    SCHEDULER = "scheduler"


class AgentMessage(BaseModel):
    """A single message in the agent conversation."""

    role: MessageRole
    agent_type: Optional[AgentType] = None
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTask(BaseModel):
    """A task dispatched to an agent by the Coordinator."""

    task_id: str
    agent_type: AgentType
    campaign_id: str
    instruction: str
    context: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    """The result returned by an agent after completing a task."""

    task_id: str
    agent_type: AgentType
    campaign_id: str
    success: bool = True
    output: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    messages: list[AgentMessage] = Field(default_factory=list)


class ClarificationQuestion(BaseModel):
    """A single clarifying question the Strategy Agent wants to ask."""

    id: str = Field(description="Unique identifier, e.g. 'q1'")
    question: str = Field(description="The question text")
    why: str = Field(default="", description="Why this information helps the strategy")


class ClarificationRequest(BaseModel):
    """Sent to the frontend when the Strategy Agent needs more info."""

    campaign_id: str
    questions: list[ClarificationQuestion] = Field(default_factory=list)
    context_summary: str = Field(
        default="",
        description="Brief summary of what the agent already understands",
    )


class ClarificationResponse(BaseModel):
    """Received from the frontend with the user's answers."""

    campaign_id: str
    answers: dict[str, str] = Field(
        default_factory=dict,
        description="Maps question id to the user's answer",
    )


class HumanReviewRequest(BaseModel):
    """Sent to the frontend when the Review/QA agent needs human input."""

    campaign_id: str
    review_summary: str
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    brand_consistency_score: float = 0.0
    requires_approval: bool = True


class HumanReviewResponse(BaseModel):
    """Received from the frontend after a human reviews the campaign."""

    campaign_id: str
    approved: bool
    notes: str = ""


class ContentPieceApproval(BaseModel):
    """Human approval decision for a single content piece."""

    piece_index: int = Field(description="Index of the piece in content.pieces")
    approved: bool = Field(description="Whether this piece is approved")
    edited_content: Optional[str] = Field(
        default=None,
        description="Edited text if the human modified the content (None = no edits)",
    )
    notes: str = Field(default="", description="Optional notes for this piece")


class ContentApprovalResponse(BaseModel):
    """Received from the frontend with per-piece approval decisions."""

    campaign_id: str
    pieces: list[ContentPieceApproval] = Field(
        default_factory=list,
        description="Approval decisions for each content piece",
    )
    reject_campaign: bool = Field(
        default=False,
        description="If True, reject the entire campaign instead of per-piece review",
    )
