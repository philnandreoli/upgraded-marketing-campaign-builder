"""
Campaign data models — represent the marketing campaign lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CampaignStatus(str, Enum):
    """Tracks where a campaign is in the pipeline."""

    DRAFT = "draft"
    CLARIFICATION = "clarification"
    STRATEGY = "strategy"
    CONTENT = "content"
    CHANNEL_PLANNING = "channel_planning"
    ANALYTICS_SETUP = "analytics_setup"
    REVIEW = "review"
    CONTENT_REVISION = "content_revision"
    CONTENT_APPROVAL = "content_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class ContentApprovalStatus(str, Enum):
    """Per-piece approval status for human content review."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ChannelType(str, Enum):
    EMAIL = "email"
    SOCIAL_MEDIA = "social_media"
    PAID_ADS = "paid_ads"
    CONTENT_MARKETING = "content_marketing"
    SEO = "seo"
    INFLUENCER = "influencer"
    EVENTS = "events"
    PR = "pr"


class SocialMediaPlatform(str, Enum):
    """Specific social-media platforms the user can target."""

    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    X = "x"
    LINKEDIN = "linkedin"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class TargetAudience(BaseModel):
    """Describes the target audience for a campaign."""

    demographics: str = Field(default="", description="Age, gender, location, income, etc.")
    psychographics: str = Field(default="", description="Interests, values, lifestyle")
    pain_points: list[str] = Field(default_factory=list)
    personas: list[str] = Field(default_factory=list)


class CampaignStrategy(BaseModel):
    """Output of the Strategy Agent."""

    objectives: list[str] = Field(default_factory=list, description="SMART campaign objectives")
    target_audience: TargetAudience = Field(default_factory=TargetAudience)
    value_proposition: str = Field(default="", description="Core value proposition")
    positioning: str = Field(default="", description="Market positioning statement")
    key_messages: list[str] = Field(default_factory=list)
    competitive_landscape: str = Field(default="")
    constraints: str = Field(default="", description="Budget, timeline, or regulatory constraints")


class ContentPiece(BaseModel):
    """A single piece of campaign content."""

    content_type: str = Field(description="e.g. headline, body_copy, cta, social_post, email_subject")
    channel: str = Field(default="")
    content: str = Field(description="The actual text content")
    variant: str = Field(default="A", description="A/B variant label")
    notes: str = Field(default="")
    approval_status: str = Field(
        default=ContentApprovalStatus.PENDING,
        description="Human approval status: pending, approved, rejected",
    )
    human_edited_content: Optional[str] = Field(
        default=None,
        description="Content edited by the human reviewer (None = no edits)",
    )
    human_notes: str = Field(
        default="",
        description="Notes from the human reviewer for this piece",
    )


class CampaignContent(BaseModel):
    """Output of the Content Creator Agent."""

    theme: str = Field(default="", description="Overall creative theme")
    tone_of_voice: str = Field(default="")
    pieces: list[ContentPiece] = Field(default_factory=list)


class PlatformBreakdown(BaseModel):
    """Per-platform budget sub-allocation for the social_media channel."""

    platform: str = Field(description="Social media platform name (e.g. instagram, facebook, x, linkedin)")
    budget_pct: float = Field(default=0.0, description="% of the social_media channel budget allocated to this platform")
    tactics: list[str] = Field(default_factory=list)
    timing: str = Field(default="", description="Platform-specific timing / cadence")


class ChannelRecommendation(BaseModel):
    """A single channel recommendation."""

    channel: ChannelType
    rationale: str = Field(default="")
    budget_pct: float = Field(default=0.0, description="Recommended % of total budget")
    timing: str = Field(default="", description="Suggested schedule / cadence")
    tactics: list[str] = Field(default_factory=list)
    platform_breakdown: Optional[list[PlatformBreakdown]] = Field(
        default=None,
        description="Per-platform budget breakdown for social_media channel (only populated when social_media platforms are specified)",
    )


class ChannelPlan(BaseModel):
    """Output of the Channel Planner Agent."""

    total_budget: float = Field(default=0.0)
    currency: str = Field(default="USD")
    recommendations: list[ChannelRecommendation] = Field(default_factory=list)
    timeline_summary: str = Field(default="")


class KPI(BaseModel):
    """A single Key Performance Indicator."""

    name: str
    target_value: str = Field(default="")
    measurement_method: str = Field(default="")


class AnalyticsPlan(BaseModel):
    """Output of the Analytics Agent."""

    kpis: list[KPI] = Field(default_factory=list)
    tracking_tools: list[str] = Field(default_factory=list)
    reporting_cadence: str = Field(default="weekly")
    attribution_model: str = Field(default="")
    success_criteria: str = Field(default="")


class ReviewFeedback(BaseModel):
    """Output of the Review / QA Agent."""

    approved: bool = False
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    brand_consistency_score: float = Field(
        default=0.0, ge=0.0, le=10.0, description="0-10 brand consistency score"
    )
    human_notes: str = Field(default="", description="Notes added by the human reviewer")


# ---------------------------------------------------------------------------
# Campaign (aggregate root)
# ---------------------------------------------------------------------------

class CampaignBrief(BaseModel):
    """Initial user input that kicks off the campaign pipeline."""

    product_or_service: str = Field(description="What is being marketed")
    goal: str = Field(description="High-level campaign goal")
    budget: Optional[float] = None
    currency: str = Field(default="USD")
    start_date: Optional[date] = Field(default=None, description="Campaign start date (ISO 8601)")
    end_date: Optional[date] = Field(default=None, description="Campaign end date (ISO 8601)")
    additional_context: str = Field(default="", description="Any extra information")
    selected_channels: list[ChannelType] = Field(
        default_factory=list,
        description="Channels the user wants to deploy to. Empty = let agents decide.",
    )
    social_media_platforms: list[SocialMediaPlatform] = Field(
        default_factory=list,
        description="Specific social-media platforms when social_media channel is selected.",
    )

    @model_validator(mode="after")
    def _validate_date_range(self) -> "CampaignBrief":
        if self.start_date is not None and self.end_date is not None:
            if self.end_date < self.start_date:
                raise ValueError("end_date must be on or after start_date")
        return self


class Campaign(BaseModel):
    """Full campaign document built progressively by the agents."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_id: Optional[str] = Field(
        default=None,
        description="Unique identifier of the user who created the campaign (JWT oid/sub).",
    )
    workspace_id: Optional[str] = Field(
        default=None,
        description="Workspace this campaign belongs to (FK to workspaces.id). None means unassigned.",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    status: CampaignStatus = CampaignStatus.DRAFT

    brief: CampaignBrief
    clarification_questions: list[dict[str, str]] = Field(
        default_factory=list,
        description="Questions the Strategy Agent asked the user.",
    )
    clarification_answers: dict[str, str] = Field(
        default_factory=dict,
        description="User answers keyed by question id.",
    )
    strategy: Optional[CampaignStrategy] = None
    content: Optional[CampaignContent] = None
    channel_plan: Optional[ChannelPlan] = None
    analytics_plan: Optional[AnalyticsPlan] = None
    review: Optional[ReviewFeedback] = None
    original_content: Optional[CampaignContent] = Field(
        default=None,
        description="Original content before review-driven revision (for comparison).",
    )
    content_revision_count: int = Field(
        default=0,
        description="Number of content revision cycles completed.",
    )
    stage_errors: dict[str, str] = Field(
        default_factory=dict,
        description="Maps stage key to error message when an agent fails.",
    )
    version: int = Field(
        default=1,
        description="Optimistic locking counter incremented on every successful write.",
    )
    wizard_step: int = Field(
        default=0,
        description="Current step in the creation wizard (0–5). Stored in the campaign JSON; no schema migration required.",
    )

    def advance_status(self, new_status: CampaignStatus) -> None:
        self.status = new_status
        self.updated_at = datetime.utcnow()
