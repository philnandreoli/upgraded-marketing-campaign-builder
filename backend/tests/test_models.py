"""
Tests for data models — CampaignBrief, Campaign, and status transitions.
"""

import pytest
from pydantic import ValidationError

from backend.models.campaign import (
    Campaign,
    CampaignBrief,
    CampaignStatus,
    CampaignStrategy,
    CampaignContent,
    ContentApprovalStatus,
    ContentPiece,
    ChannelPlan,
    ChannelRecommendation,
    ChannelType,
    AnalyticsPlan,
    KPI,
    ReviewFeedback,
    SocialMediaPlatform,
    TargetAudience,
)
from backend.models.messages import (
    AgentType, AgentTask, AgentResult, AgentMessage, MessageRole,
    ContentPieceApproval, ContentApprovalResponse,
)
from backend.models.user import User, UserRole


# ---- CampaignBrief ----

class TestCampaignBrief:
    def test_minimal_brief(self):
        b = CampaignBrief(product_or_service="Widget", goal="Sell more")
        assert b.product_or_service == "Widget"
        assert b.budget is None
        assert b.currency == "USD"

    def test_full_brief(self):
        b = CampaignBrief(
            product_or_service="CloudSync",
            goal="Growth",
            budget=50000,
            currency="EUR",
            start_date="2026-04-01",
            end_date="2026-06-30",
            additional_context="EMEA focus",
        )
        assert b.budget == 50000
        assert b.currency == "EUR"

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError):
            CampaignBrief(product_or_service="X")  # missing goal

    def test_selected_channels_default_empty(self):
        b = CampaignBrief(product_or_service="Widget", goal="Sell more")
        assert b.selected_channels == []

    def test_selected_channels_valid(self):
        b = CampaignBrief(
            product_or_service="Widget",
            goal="Sell more",
            selected_channels=["email", "seo", "paid_ads"],
        )
        assert len(b.selected_channels) == 3
        assert b.selected_channels[0] == ChannelType.EMAIL

    def test_selected_channels_invalid_raises(self):
        with pytest.raises(ValidationError):
            CampaignBrief(
                product_or_service="Widget",
                goal="Sell more",
                selected_channels=["invalid_channel"],
            )

    def test_social_media_platforms_default_empty(self):
        b = CampaignBrief(product_or_service="Widget", goal="Sell more")
        assert b.social_media_platforms == []

    def test_social_media_platforms_valid(self):
        b = CampaignBrief(
            product_or_service="Widget",
            goal="Sell more",
            selected_channels=["social_media"],
            social_media_platforms=["facebook", "x"],
        )
        assert len(b.social_media_platforms) == 2
        assert b.social_media_platforms[0] == SocialMediaPlatform.FACEBOOK
        assert b.social_media_platforms[1] == SocialMediaPlatform.X

    def test_social_media_platforms_invalid_raises(self):
        with pytest.raises(ValidationError):
            CampaignBrief(
                product_or_service="Widget",
                goal="Sell more",
                social_media_platforms=["tiktok"],
            )

    def test_start_end_date_valid(self):
        b = CampaignBrief(
            product_or_service="Widget",
            goal="Sell more",
            start_date="2026-04-01",
            end_date="2026-06-30",
        )
        from datetime import date
        assert b.start_date == date(2026, 4, 1)
        assert b.end_date == date(2026, 6, 30)

    def test_start_end_date_same_day_valid(self):
        b = CampaignBrief(
            product_or_service="Widget",
            goal="Sell more",
            start_date="2026-04-01",
            end_date="2026-04-01",
        )
        assert b.start_date == b.end_date

    def test_end_date_before_start_date_raises(self):
        with pytest.raises(ValidationError):
            CampaignBrief(
                product_or_service="Widget",
                goal="Sell more",
                start_date="2026-06-30",
                end_date="2026-04-01",
            )

    def test_dates_optional(self):
        b = CampaignBrief(product_or_service="Widget", goal="Sell more")
        assert b.start_date is None
        assert b.end_date is None

    def test_only_start_date_no_validation_error(self):
        b = CampaignBrief(
            product_or_service="Widget",
            goal="Sell more",
            start_date="2026-04-01",
        )
        assert b.start_date is not None
        assert b.end_date is None


# ---- Campaign ----

class TestCampaign:
    def test_defaults(self):
        brief = CampaignBrief(product_or_service="X", goal="Y")
        c = Campaign(brief=brief)
        assert c.status == CampaignStatus.DRAFT
        assert c.id is not None
        assert c.strategy is None
        assert c.content is None

    def test_advance_status(self):
        brief = CampaignBrief(product_or_service="X", goal="Y")
        c = Campaign(brief=brief)
        old_updated = c.updated_at
        c.advance_status(CampaignStatus.STRATEGY)
        assert c.status == CampaignStatus.STRATEGY
        assert c.updated_at >= old_updated

    def test_model_dump_roundtrip(self):
        brief = CampaignBrief(product_or_service="X", goal="Y")
        c = Campaign(brief=brief)
        data = c.model_dump(mode="json")
        assert data["status"] == "draft"
        assert data["brief"]["product_or_service"] == "X"
        # Roundtrip
        c2 = Campaign.model_validate(data)
        assert c2.id == c.id


# ---- Sub-models ----

class TestSubModels:
    def test_strategy(self):
        s = CampaignStrategy(
            objectives=["Increase revenue by 20%"],
            value_proposition="Best cloud storage",
            positioning="Enterprise-first",
            key_messages=["Fast", "Secure"],
        )
        assert len(s.objectives) == 1
        assert s.target_audience.demographics == ""

    def test_content_piece(self):
        cp = ContentPiece(
            content_type="headline",
            content="CloudSync — Your Data, Everywhere",
        )
        assert cp.variant == "A"
        assert cp.channel == ""

    def test_channel_recommendation(self):
        cr = ChannelRecommendation(
            channel=ChannelType.EMAIL,
            rationale="High ROI",
            budget_pct=25.0,
        )
        assert cr.channel == ChannelType.EMAIL

    def test_kpi(self):
        k = KPI(name="Conversion Rate", target_value="5%")
        assert k.measurement_method == ""

    def test_review_feedback_score_bounds(self):
        # Valid score
        r = ReviewFeedback(brand_consistency_score=7.5)
        assert r.brand_consistency_score == 7.5

        # Out of bounds
        with pytest.raises(ValidationError):
            ReviewFeedback(brand_consistency_score=11.0)

        with pytest.raises(ValidationError):
            ReviewFeedback(brand_consistency_score=-1.0)


# ---- Messages ----

class TestMessages:
    def test_agent_task(self):
        t = AgentTask(
            task_id="t1",
            agent_type=AgentType.STRATEGY,
            campaign_id="c1",
            instruction="Do strategy",
        )
        assert t.agent_type == AgentType.STRATEGY

    def test_agent_result_success(self):
        r = AgentResult(
            task_id="t1",
            agent_type=AgentType.STRATEGY,
            campaign_id="c1",
            success=True,
            output={"objectives": ["Grow"]},
        )
        assert r.success
        assert r.error is None

    def test_agent_result_failure(self):
        r = AgentResult(
            task_id="t1",
            agent_type=AgentType.STRATEGY,
            campaign_id="c1",
            success=False,
            error="LLM timeout",
        )
        assert not r.success
        assert "timeout" in r.error


# ---- Content Approval Models ----

class TestContentApprovalStatus:
    def test_enum_values(self):
        assert ContentApprovalStatus.PENDING.value == "pending"
        assert ContentApprovalStatus.APPROVED.value == "approved"
        assert ContentApprovalStatus.REJECTED.value == "rejected"


class TestContentPieceApprovalFields:
    def test_content_piece_approval_status_default(self):
        cp = ContentPiece(
            content_type="headline",
            content="Test Content",
        )
        assert cp.approval_status == ContentApprovalStatus.PENDING
        assert cp.human_edited_content is None
        assert cp.human_notes == ""

    def test_content_piece_with_approval(self):
        cp = ContentPiece(
            content_type="headline",
            content="Test Content",
            approval_status=ContentApprovalStatus.APPROVED,
            human_edited_content="Edited Test",
            human_notes="Looks great",
        )
        assert cp.approval_status == ContentApprovalStatus.APPROVED
        assert cp.human_edited_content == "Edited Test"

    def test_content_piece_roundtrip(self):
        cp = ContentPiece(
            content_type="headline",
            content="Original",
            approval_status=ContentApprovalStatus.REJECTED,
            human_notes="Needs more punch",
        )
        data = cp.model_dump(mode="json")
        assert data["approval_status"] == "rejected"
        cp2 = ContentPiece.model_validate(data)
        assert cp2.approval_status == ContentApprovalStatus.REJECTED


class TestCampaignOriginalContent:
    def test_campaign_original_content_default_none(self):
        brief = CampaignBrief(product_or_service="X", goal="Y")
        c = Campaign(brief=brief)
        assert c.original_content is None
        assert c.content_revision_count == 0

    def test_campaign_original_content_set(self):
        brief = CampaignBrief(product_or_service="X", goal="Y")
        c = Campaign(brief=brief)
        c.original_content = CampaignContent(
            theme="Old Theme",
            tone_of_voice="Formal",
            pieces=[ContentPiece(content_type="headline", content="Old Headline")],
        )
        c.content_revision_count = 1
        data = c.model_dump(mode="json")
        assert data["original_content"]["theme"] == "Old Theme"
        assert data["content_revision_count"] == 1

    def test_campaign_status_content_revision(self):
        brief = CampaignBrief(product_or_service="X", goal="Y")
        c = Campaign(brief=brief)
        c.advance_status(CampaignStatus.CONTENT_REVISION)
        assert c.status == CampaignStatus.CONTENT_REVISION

    def test_campaign_status_content_approval(self):
        brief = CampaignBrief(product_or_service="X", goal="Y")
        c = Campaign(brief=brief)
        c.advance_status(CampaignStatus.CONTENT_APPROVAL)
        assert c.status == CampaignStatus.CONTENT_APPROVAL


class TestContentApprovalMessages:
    def test_piece_approval(self):
        pa = ContentPieceApproval(
            piece_index=0,
            approved=True,
            edited_content="Edited",
            notes="LGTM",
        )
        assert pa.piece_index == 0
        assert pa.approved is True
        assert pa.edited_content == "Edited"

    def test_approval_response(self):
        resp = ContentApprovalResponse(
            campaign_id="c1",
            pieces=[
                ContentPieceApproval(piece_index=0, approved=True),
                ContentPieceApproval(piece_index=1, approved=False, notes="Fix tone"),
            ],
            reject_campaign=False,
        )
        assert len(resp.pieces) == 2
        assert resp.reject_campaign is False

    def test_approval_response_reject_campaign(self):
        resp = ContentApprovalResponse(
            campaign_id="c1",
            reject_campaign=True,
        )
        assert resp.reject_campaign is True
        assert resp.pieces == []


class TestCampaignStatusEnum:
    def test_manual_review_required_value(self):
        assert CampaignStatus.MANUAL_REVIEW_REQUIRED.value == "manual_review_required"

    def test_manual_review_required_serializes(self):
        brief = CampaignBrief(product_or_service="X", goal="Y")
        c = Campaign(brief=brief)
        c.advance_status(CampaignStatus.MANUAL_REVIEW_REQUIRED)
        assert c.status == CampaignStatus.MANUAL_REVIEW_REQUIRED
        data = c.model_dump(mode="json")
        assert data["status"] == "manual_review_required"
        c2 = Campaign.model_validate(data)
        assert c2.status == CampaignStatus.MANUAL_REVIEW_REQUIRED


# ---- User model ----

class TestUserRole:
    def test_enum_values(self):
        assert UserRole.ADMIN.value == "admin"
        assert UserRole.CAMPAIGN_BUILDER.value == "campaign_builder"
        assert UserRole.VIEWER.value == "viewer"

    def test_str_coercion(self):
        assert UserRole("admin") == UserRole.ADMIN
        assert UserRole("campaign_builder") == UserRole.CAMPAIGN_BUILDER
        assert UserRole("viewer") == UserRole.VIEWER

    def test_invalid_role_raises(self):
        with pytest.raises(ValueError):
            UserRole("superuser")


class TestUserModel:
    def test_defaults(self):
        u = User(id="oid-123")
        assert u.id == "oid-123"
        assert UserRole.VIEWER in u.roles
        assert u.is_active is True
        assert u.email is None
        assert u.display_name is None

    def test_full_user(self):
        u = User(
            id="oid-456",
            email="alice@example.com",
            display_name="Alice",
            roles=[UserRole.ADMIN],
            is_active=True,
        )
        assert u.email == "alice@example.com"
        assert u.display_name == "Alice"
        assert UserRole.ADMIN in u.roles

    def test_missing_id_raises(self):
        with pytest.raises(ValidationError):
            User()  # id is required

    def test_roundtrip(self):
        u = User(
            id="oid-789",
            email="bob@example.com",
            display_name="Bob",
            roles=[UserRole.CAMPAIGN_BUILDER],
        )
        data = u.model_dump(mode="json")
        assert data["roles"] == ["campaign_builder"]
        u2 = User.model_validate(data)
        assert u2.id == u.id
        assert UserRole.CAMPAIGN_BUILDER in u2.roles

    def test_inactive_user(self):
        u = User(id="oid-000", is_active=False)
        assert u.is_active is False


# ---- Event models ----

from backend.models.events import (
    ClarificationRequestedEvent,
    ContentApprovalRequestedEvent,
    StageCompletedEvent,
    StageErrorEvent,
    StageStartedEvent,
    WorkflowEvent,
)


class TestWorkflowEventBase:
    def test_defaults(self):
        evt = WorkflowEvent(event_type="test_event", campaign_id="camp-1")
        assert evt.event_type == "test_event"
        assert evt.campaign_id == "camp-1"
        assert evt.version == "1.0"
        assert evt.payload == {}
        assert evt.timestamp.tzinfo is not None

    def test_serialises_to_dict(self):
        evt = WorkflowEvent(event_type="test_event", campaign_id="camp-1")
        data = evt.model_dump(mode="json")
        assert data["event_type"] == "test_event"
        assert data["campaign_id"] == "camp-1"
        assert data["version"] == "1.0"
        assert "timestamp" in data


class TestStageStartedEvent:
    def test_fields(self):
        evt = StageStartedEvent(campaign_id="c1", stage="strategy")
        assert evt.event_type == "stage_started"
        assert evt.stage == "strategy"
        assert evt.campaign_id == "c1"

    def test_is_superset_of_legacy_payload(self):
        """Serialised dict must contain all fields from the old untyped payload."""
        evt = StageStartedEvent(campaign_id="c1", stage="strategy")
        data = evt.model_dump(mode="json")
        assert data["campaign_id"] == "c1"
        assert data["stage"] == "strategy"


class TestStageCompletedEvent:
    def test_fields(self):
        output = {"key": "value"}
        evt = StageCompletedEvent(campaign_id="c2", stage="content", output=output)
        assert evt.event_type == "stage_completed"
        assert evt.stage == "content"
        assert evt.output == output

    def test_output_defaults_empty(self):
        evt = StageCompletedEvent(campaign_id="c2", stage="content")
        assert evt.output == {}

    def test_is_superset_of_legacy_payload(self):
        output = {"pieces": []}
        evt = StageCompletedEvent(campaign_id="c2", stage="content", output=output)
        data = evt.model_dump(mode="json")
        assert data["campaign_id"] == "c2"
        assert data["stage"] == "content"
        assert data["output"] == output


class TestStageErrorEvent:
    def test_fields(self):
        evt = StageErrorEvent(campaign_id="c3", stage="analytics_setup", error="LLM timeout")
        assert evt.event_type == "stage_error"
        assert evt.stage == "analytics_setup"
        assert evt.error == "LLM timeout"

    def test_is_superset_of_legacy_payload(self):
        evt = StageErrorEvent(campaign_id="c3", stage="analytics_setup", error="oops")
        data = evt.model_dump(mode="json")
        assert data["campaign_id"] == "c3"
        assert data["stage"] == "analytics_setup"
        assert data["error"] == "oops"


class TestClarificationRequestedEvent:
    def test_fields(self):
        questions = [{"id": "q1", "question": "Who is your audience?"}]
        evt = ClarificationRequestedEvent(
            campaign_id="c4",
            questions=questions,
            context_summary="Need more info",
        )
        assert evt.event_type == "clarification_requested"
        assert evt.questions == questions
        assert evt.context_summary == "Need more info"

    def test_context_summary_defaults_empty(self):
        evt = ClarificationRequestedEvent(campaign_id="c4", questions=[])
        assert evt.context_summary == ""

    def test_is_superset_of_legacy_payload(self):
        questions = [{"id": "q1", "question": "Target?"}]
        evt = ClarificationRequestedEvent(
            campaign_id="c4",
            questions=questions,
            context_summary="summary",
        )
        data = evt.model_dump(mode="json")
        assert data["campaign_id"] == "c4"
        assert data["questions"] == questions
        assert data["context_summary"] == "summary"


class TestContentApprovalRequestedEvent:
    def test_fields(self):
        content = {"theme": "Test", "pieces": []}
        evt = ContentApprovalRequestedEvent(
            campaign_id="c5",
            content=content,
            revision_cycle=1,
        )
        assert evt.event_type == "content_approval_requested"
        assert evt.content == content
        assert evt.revision_cycle == 1

    def test_defaults(self):
        evt = ContentApprovalRequestedEvent(campaign_id="c5")
        assert evt.content == {}
        assert evt.revision_cycle == 0

    def test_is_superset_of_legacy_payload(self):
        content = {"pieces": []}
        evt = ContentApprovalRequestedEvent(
            campaign_id="c5",
            content=content,
            revision_cycle=2,
        )
        data = evt.model_dump(mode="json")
        assert data["campaign_id"] == "c5"
        assert data["content"] == content
        assert data["revision_cycle"] == 2
