"""
Integration test for the CoordinatorAgent pipeline.

Mocks all LLM calls so it runs fully offline. Verifies:
- Pipeline runs all stages in order
- Campaign status transitions correctly
- Events are emitted for each stage
- Content-revision stage produces revised content automatically
- Human per-piece content approval / rejection works
"""

import asyncio
import json
import pytest
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from backend.agents.coordinator_agent import CoordinatorAgent
from backend.models.campaign import Campaign, CampaignBrief, CampaignStatus, ContentApprovalStatus
from backend.models.messages import ClarificationResponse, ContentApprovalResponse, ContentPieceApproval
from backend.models.workflow import WorkflowCheckpoint, WorkflowWaitType
from backend.tests.mock_store import InMemoryCampaignStore


# ---- Mock LLM responses for each stage ----

STRATEGY_RESPONSE = json.dumps({
    "objectives": ["Increase signups by 30% in Q2"],
    "target_audience": {
        "demographics": "25-45, tech professionals",
        "psychographics": "Productivity-focused",
        "pain_points": ["Data silos", "Collaboration friction"],
        "personas": ["IT Manager Maria", "Startup CTO Dave"],
    },
    "value_proposition": "Seamless cloud collaboration for modern teams",
    "positioning": "Enterprise-grade simplicity",
    "key_messages": ["Work from anywhere", "Bank-level security"],
    "competitive_landscape": "Competing with Dropbox, Box, Google Drive",
    "constraints": "USD 50K budget, 3-month timeline",
})

CONTENT_RESPONSE = json.dumps({
    "theme": "Unleash Your Team",
    "tone_of_voice": "Professional yet approachable",
    "pieces": [
        {"content_type": "headline", "channel": "email", "content": "Sync Without Limits", "variant": "A", "notes": ""},
        {"content_type": "cta", "channel": "website", "content": "Start Free Trial", "variant": "A", "notes": ""},
    ],
})

CHANNEL_RESPONSE = json.dumps({
    "total_budget": 50000,
    "currency": "USD",
    "recommendations": [
        {"channel": "email", "rationale": "High ROI for B2B", "budget_pct": 25, "timing": "Week 1-12", "tactics": ["Drip series"]},
        {"channel": "paid_ads", "rationale": "Quick reach", "budget_pct": 40, "timing": "Week 1-8", "tactics": ["LinkedIn Ads"]},
        {"channel": "content_marketing", "rationale": "Thought leadership", "budget_pct": 20, "timing": "Week 1-12", "tactics": ["Blog posts"]},
        {"channel": "social_media", "rationale": "Brand awareness", "budget_pct": 15, "timing": "Ongoing", "tactics": ["LinkedIn, Twitter"]},
    ],
    "timeline_summary": "12-week phased campaign",
})

ANALYTICS_RESPONSE = json.dumps({
    "kpis": [
        {"name": "Signup Rate", "target_value": "5%", "measurement_method": "GA4 conversion tracking"},
        {"name": "CPA", "target_value": "$50", "measurement_method": "Ad platform reporting"},
    ],
    "tracking_tools": ["Google Analytics 4", "HubSpot"],
    "reporting_cadence": "weekly",
    "attribution_model": "multi-touch linear",
    "success_criteria": "30% increase in qualified signups",
})

REVIEW_RESPONSE = json.dumps({
    "approved": True,
    "issues": ["Minor tone inconsistency in CTA"],
    "suggestions": ["Consider adding video content for social channels"],
    "brand_consistency_score": 8.5,
    "review_summary": "Well-constructed campaign with strong strategic alignment",
    "requires_human_approval": True,
})

# Content revision response (after review feedback is fed back to content creator)
CONTENT_REVISION_RESPONSE = json.dumps({
    "theme": "Unleash Your Team — Revised",
    "tone_of_voice": "Professional yet approachable",
    "pieces": [
        {"content_type": "headline", "channel": "email", "content": "Sync Without Limits — Improved", "variant": "A", "notes": ""},
        {"content_type": "cta", "channel": "website", "content": "Start Your Free Trial Today", "variant": "A", "notes": ""},
    ],
})

# Clarification pass — no follow-up questions needed
CLARIFICATION_RESPONSE = json.dumps({
    "needs_clarification": False,
    "context_summary": "Brief is detailed enough",
    "questions": [],
})

# Piece-level revision response for a single rejected piece
PIECE_REVISION_RESPONSE = json.dumps({
    "theme": "Unleash Your Team — Revised",
    "tone_of_voice": "Professional yet approachable",
    "pieces": [
        {"content_type": "cta", "channel": "website", "content": "Try CloudSync Free — No Credit Card", "variant": "A", "notes": ""},
    ],
})


def _stage_responses():
    """Return a side_effect list matching the pipeline stage order.

    The first call is the clarification pass (Strategy Agent), followed
    by the pipeline stages: Strategy, Content, Channel, Analytics, Review,
    then the automatic Content Revision.
    """
    return [
        CLARIFICATION_RESPONSE,
        STRATEGY_RESPONSE,
        CONTENT_RESPONSE,
        CHANNEL_RESPONSE,
        ANALYTICS_RESPONSE,
        REVIEW_RESPONSE,
        CONTENT_REVISION_RESPONSE,
    ]


@pytest.fixture
def store():
    return InMemoryCampaignStore()


@pytest.fixture
def brief():
    return CampaignBrief(
        product_or_service="CloudSync — cloud storage for teams",
        goal="Increase enterprise signups by 30% in Q2",
        budget=50000,
        currency="USD",
        start_date="2026-04-01",
        end_date="2026-06-30",
    )


@pytest.fixture
def events_log():
    """Collects emitted events for assertions."""
    return []


@pytest.fixture
def mock_on_event(events_log):
    async def _on_event(event: str, data: dict):
        events_log.append({"event": event, **data})
    return _on_event


class TestCoordinatorPipeline:
    @pytest.mark.asyncio
    async def test_full_pipeline_with_approval(self, store, brief, events_log, mock_on_event):
        """Run the full pipeline and approve all pieces at the content-approval gate."""
        campaign = await store.create(brief)

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat_json = AsyncMock(side_effect=_stage_responses())
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(store=store, on_event=mock_on_event)

            # Schedule human approval of all pieces after a short delay
            async def _auto_approve():
                await asyncio.sleep(0.3)
                await coordinator.submit_content_approval(
                    ContentApprovalResponse(
                        campaign_id=campaign.id,
                        pieces=[
                            ContentPieceApproval(piece_index=0, approved=True, notes="Great headline"),
                            ContentPieceApproval(piece_index=1, approved=True, notes="Good CTA"),
                        ],
                        reject_campaign=False,
                    )
                )

            approve_task = asyncio.create_task(_auto_approve())

            result = await coordinator.run_pipeline(campaign)
            await approve_task

        # Final status
        assert result.status == CampaignStatus.APPROVED

        # All sections populated
        assert result.strategy is not None
        assert len(result.strategy.objectives) > 0
        assert result.content is not None
        assert len(result.content.pieces) > 0
        assert result.channel_plan is not None
        assert len(result.channel_plan.recommendations) > 0
        assert result.analytics_plan is not None
        assert len(result.analytics_plan.kpis) > 0
        assert result.review is not None

        # Original content preserved
        assert result.original_content is not None
        assert result.content_revision_count >= 1

        # Revised content should be the improved version
        assert "Improved" in result.content.pieces[0].content or "Today" in result.content.pieces[1].content

        # All pieces should be approved
        for piece in result.content.pieces:
            assert piece.approval_status == ContentApprovalStatus.APPROVED

        # Events emitted
        event_names = [e["event"] for e in events_log]
        assert "pipeline_started" in event_names
        assert "pipeline_completed" in event_names
        assert "content_approval_requested" in event_names
        assert "content_approval_completed" in event_names

        # Persisted in store
        stored = await store.get(campaign.id)
        assert stored.status == CampaignStatus.APPROVED

    @pytest.mark.asyncio
    async def test_full_pipeline_with_campaign_rejection(self, store, brief, events_log, mock_on_event):
        """Run the pipeline and reject the entire campaign at the content-approval gate."""
        campaign = await store.create(brief)

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat_json = AsyncMock(side_effect=_stage_responses())
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(store=store, on_event=mock_on_event)

            async def _auto_reject():
                await asyncio.sleep(0.3)
                await coordinator.submit_content_approval(
                    ContentApprovalResponse(
                        campaign_id=campaign.id,
                        reject_campaign=True,
                    )
                )

            reject_task = asyncio.create_task(_auto_reject())
            result = await coordinator.run_pipeline(campaign)
            await reject_task

        assert result.status == CampaignStatus.REJECTED

    @pytest.mark.asyncio
    async def test_pipeline_piece_rejection_triggers_rerevision(self, store, brief, events_log, mock_on_event):
        """Reject one piece → AI re-revises → approve all on second round."""
        campaign = await store.create(brief)

        call_count = 0

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            # Normal pipeline + content revision + piece re-revision
            responses = _stage_responses() + [PIECE_REVISION_RESPONSE]
            mock_llm.chat_json = AsyncMock(side_effect=responses)
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(store=store, on_event=mock_on_event)

            approval_round = 0

            async def _auto_approve_with_reject():
                nonlocal approval_round
                while True:
                    await asyncio.sleep(0.3)
                    approval_round += 1
                    if approval_round == 1:
                        # First round: approve piece 0, reject piece 1
                        await coordinator.submit_content_approval(
                            ContentApprovalResponse(
                                campaign_id=campaign.id,
                                pieces=[
                                    ContentPieceApproval(piece_index=0, approved=True, notes="Good"),
                                    ContentPieceApproval(piece_index=1, approved=False, notes="CTA needs work"),
                                ],
                                reject_campaign=False,
                            )
                        )
                    else:
                        # Second round: approve all remaining
                        await coordinator.submit_content_approval(
                            ContentApprovalResponse(
                                campaign_id=campaign.id,
                                pieces=[
                                    ContentPieceApproval(piece_index=1, approved=True, notes="Better now"),
                                ],
                                reject_campaign=False,
                            )
                        )
                        break

            approve_task = asyncio.create_task(_auto_approve_with_reject())
            result = await coordinator.run_pipeline(campaign)
            await approve_task

        assert result.status == CampaignStatus.APPROVED
        # All pieces approved
        for piece in result.content.pieces:
            assert piece.approval_status == ContentApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_pipeline_max_revision_cycles_escalates_to_manual_review(
        self, store, brief, events_log, mock_on_event
    ):
        """Reject a piece every round until MAX_CONTENT_REVISION_CYCLES is exhausted.

        The coordinator must transition to MANUAL_REVIEW_REQUIRED instead of
        auto-approving, and the emitted event must carry approved=False and
        needs_manual_review=True.
        """
        from backend.agents.coordinator_agent import MAX_CONTENT_REVISION_CYCLES

        campaign = await store.create(brief)

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            # Normal pipeline stages + one piece-revision response per approval cycle
            responses = _stage_responses() + [PIECE_REVISION_RESPONSE] * MAX_CONTENT_REVISION_CYCLES
            mock_llm.chat_json = AsyncMock(side_effect=responses)
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(store=store, on_event=mock_on_event)

            async def _always_reject():
                # Keep rejecting piece 1 on every approval round until the pipeline ends
                while True:
                    await asyncio.sleep(0.3)
                    try:
                        await coordinator.submit_content_approval(
                            ContentApprovalResponse(
                                campaign_id=campaign.id,
                                pieces=[
                                    ContentPieceApproval(piece_index=0, approved=True),
                                    ContentPieceApproval(piece_index=1, approved=False, notes="Still not good"),
                                ],
                                reject_campaign=False,
                            )
                        )
                    except Exception:
                        break

            reject_task = asyncio.create_task(_always_reject())
            result = await coordinator.run_pipeline(campaign)
            reject_task.cancel()
            try:
                await reject_task
            except asyncio.CancelledError:
                pass

        assert result.status == CampaignStatus.MANUAL_REVIEW_REQUIRED

        # The emitted event must signal manual review, not approval
        approval_events = [e for e in events_log if e["event"] == "content_approval_completed"]
        assert approval_events, "content_approval_completed event must be emitted"
        last_event = approval_events[-1]
        assert last_event["approved"] is False
        assert last_event.get("needs_manual_review") is True

    @pytest.mark.asyncio
    async def test_pipeline_handles_stage_failure(self, store, brief, events_log, mock_on_event):
        """If strategy fails, the pipeline should stop — no downstream stages should run."""
        campaign = await store.create(brief)

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            # Clarification skipped, strategy fails immediately
            mock_llm.chat_json = AsyncMock(
                side_effect=[
                    CLARIFICATION_RESPONSE,
                    Exception("Strategy LLM Error"),
                ]
            )
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(store=store, on_event=mock_on_event)
            result = await coordinator.run_pipeline(campaign)

        # Strategy failed — recorded in stage_errors
        assert "strategy" in result.stage_errors

        # Downstream stages must NOT have run (pipeline short-circuited)
        assert result.strategy is None
        assert result.content is None
        assert result.channel_plan is None
        assert result.analytics_plan is None

        # LLM called exactly twice: once for clarification, once for strategy
        assert mock_llm.chat_json.call_count == 2

        # Stage error event emitted, but no stage_started for content/channel/analytics/review
        event_names = [e["event"] for e in events_log]
        assert "stage_error" in event_names
        stage_started_stages = [
            e.get("stage")
            for e in events_log
            if e["event"] == "stage_started"
        ]
        assert "content" not in stage_started_stages
        assert "channel_planning" not in stage_started_stages
        assert "analytics_setup" not in stage_started_stages
        assert "review" not in stage_started_stages


class TestCoordinatorContentApproval:
    @pytest.mark.asyncio
    async def test_submit_approval_no_pending(self, store):
        """Submitting approval when there's no pending future should not crash."""
        coordinator = CoordinatorAgent(store=store)
        await coordinator.submit_content_approval(
            ContentApprovalResponse(
                campaign_id="nonexistent",
                pieces=[],
            )
        )
        # Should complete without error


class TestStatusTransitions:
    @pytest.mark.asyncio
    async def test_status_progresses_through_stages(self, store, brief, events_log, mock_on_event):
        """Track status transitions during pipeline execution."""
        campaign = await store.create(brief)
        statuses_seen = []

        async def _tracking_event(event, data):
            events_log.append({"event": event, **data})
            c = await store.get(campaign.id)
            if c:
                statuses_seen.append(c.status.value)

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat_json = AsyncMock(side_effect=_stage_responses())
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(store=store, on_event=_tracking_event)

            async def _auto_approve():
                await asyncio.sleep(0.3)
                await coordinator.submit_content_approval(
                    ContentApprovalResponse(
                        campaign_id=campaign.id,
                        pieces=[
                            ContentPieceApproval(piece_index=0, approved=True),
                            ContentPieceApproval(piece_index=1, approved=True),
                        ],
                    )
                )

            task = asyncio.create_task(_auto_approve())
            await coordinator.run_pipeline(campaign)
            await task

        # Verify we progressed through the expected status sequence
        assert "strategy" in statuses_seen
        assert "content" in statuses_seen
        assert "channel_planning" in statuses_seen
        assert "analytics_setup" in statuses_seen
        assert "review" in statuses_seen
        assert "content_revision" in statuses_seen


# Clarification response that requests follow-up questions
CLARIFICATION_WITH_QUESTIONS_RESPONSE = json.dumps({
    "needs_clarification": True,
    "context_summary": "Need more info about target audience",
    "questions": [
        {"id": "q1", "question": "Who is your primary target audience?"},
    ],
})


class TestCoordinatorClarificationResume:
    @pytest.mark.asyncio
    async def test_run_clarification_skips_wait_when_answers_already_present(
        self, store, brief, events_log, mock_on_event
    ):
        """If clarification_answers are already populated, the pipeline should skip
        the future-based wait and continue immediately without blocking."""
        campaign = await store.create(brief)
        # Pre-populate answers as if the user had already submitted them
        campaign.clarification_answers = {"q1": "Our audience is B2B tech companies"}
        await store.update(campaign)

        # Responses: clarification asks questions, then the normal pipeline stages
        responses = [
            CLARIFICATION_WITH_QUESTIONS_RESPONSE,
            STRATEGY_RESPONSE,
            CONTENT_RESPONSE,
            CHANNEL_RESPONSE,
            ANALYTICS_RESPONSE,
            REVIEW_RESPONSE,
            CONTENT_REVISION_RESPONSE,
        ]

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat_json = AsyncMock(side_effect=responses)
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(store=store, on_event=mock_on_event)

            # Schedule auto-approval for the content gate
            async def _auto_approve():
                await asyncio.sleep(0.3)
                await coordinator.submit_content_approval(
                    ContentApprovalResponse(
                        campaign_id=campaign.id,
                        pieces=[
                            ContentPieceApproval(piece_index=0, approved=True),
                            ContentPieceApproval(piece_index=1, approved=True),
                        ],
                    )
                )

            approve_task = asyncio.create_task(_auto_approve())
            result = await coordinator.run_pipeline(campaign)
            await approve_task

        # Pipeline should have completed successfully without hanging
        assert result.status == CampaignStatus.APPROVED
        assert result.strategy is not None

        event_names = [e["event"] for e in events_log]
        assert "clarification_completed" in event_names
        # clarification_requested should NOT have been emitted (answers already present)
        assert "clarification_requested" not in event_names

    @pytest.mark.asyncio
    async def test_submit_clarification_relaunches_pipeline_when_no_future(
        self, store, brief, events_log, mock_on_event
    ):
        """When no pending future exists (user navigated away and returned),
        submit_clarification should persist the answers and re-launch the pipeline."""
        campaign = await store.create(brief)
        # Simulate a campaign stuck in clarification status with questions set
        campaign.clarification_questions = [{"id": "q1", "question": "Target audience?"}]
        campaign.advance_status(CampaignStatus.CLARIFICATION)
        await store.update(campaign)

        # Responses for the re-launched pipeline (clarification skipped because
        # answers are now present, then normal stages)
        responses = [
            CLARIFICATION_WITH_QUESTIONS_RESPONSE,
            STRATEGY_RESPONSE,
            CONTENT_RESPONSE,
            CHANNEL_RESPONSE,
            ANALYTICS_RESPONSE,
            REVIEW_RESPONSE,
            CONTENT_REVISION_RESPONSE,
        ]

        pipeline_completed = asyncio.Event()
        result_holder = []

        async def _tracking_event(event, data):
            events_log.append({"event": event, **data})
            if event == "pipeline_completed":
                pipeline_completed.set()

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat_json = AsyncMock(side_effect=responses)
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(store=store, on_event=_tracking_event)

            # Schedule auto-approval for the content gate
            async def _auto_approve():
                await asyncio.sleep(0.5)
                await coordinator.submit_content_approval(
                    ContentApprovalResponse(
                        campaign_id=campaign.id,
                        pieces=[
                            ContentPieceApproval(piece_index=0, approved=True),
                            ContentPieceApproval(piece_index=1, approved=True),
                        ],
                    )
                )

            approve_task = asyncio.create_task(_auto_approve())

            # Submit clarification with no active pipeline future — should re-launch
            await coordinator.submit_clarification(
                ClarificationResponse(
                    campaign_id=campaign.id,
                    answers={"q1": "B2B tech companies"},
                )
            )

            # Wait for the re-launched pipeline to finish
            await asyncio.wait_for(pipeline_completed.wait(), timeout=5.0)
            await approve_task

        # Answers should be persisted
        updated = await store.get(campaign.id)
        assert updated.clarification_answers == {"q1": "B2B tech companies"}

        # Pipeline should have completed
        event_names = [e["event"] for e in events_log]
        assert "pipeline_completed" in event_names

    @pytest.mark.asyncio
    async def test_submit_clarification_no_op_when_campaign_not_found(self, store):
        """submit_clarification should not crash when the campaign does not exist."""
        coordinator = CoordinatorAgent(store=store)
        # Should complete without raising any exception
        await coordinator.submit_clarification(
            ClarificationResponse(
                campaign_id="nonexistent-id",
                answers={"q1": "Answer"},
            )
        )


class TestTransitionValidation:
    """Tests for the ALLOWED_TRANSITIONS map and _transition() helper."""

    def test_valid_transition_succeeds(self, store):
        """A transition listed in ALLOWED_TRANSITIONS should apply without warning."""
        from backend.agents.coordinator_agent import ALLOWED_TRANSITIONS

        coordinator = CoordinatorAgent(store=store)
        campaign = Campaign(
            brief=CampaignBrief(
                product_or_service="Test",
                goal="Test goal",
                budget=1000,
                currency="USD",
                start_date="2026-01-01",
                end_date="2026-03-31",
            )
        )
        # DRAFT -> STRATEGY is a valid transition
        assert CampaignStatus.STRATEGY in ALLOWED_TRANSITIONS[CampaignStatus.DRAFT]

        import logging
        with patch("backend.agents.coordinator_agent.logger") as mock_logger:
            coordinator._transition(campaign, CampaignStatus.STRATEGY)

        assert campaign.status == CampaignStatus.STRATEGY
        mock_logger.warning.assert_not_called()

    def test_invalid_transition_logs_warning_but_proceeds(self, store):
        """An invalid transition should log a warning but still update the status."""
        coordinator = CoordinatorAgent(store=store)
        campaign = Campaign(
            brief=CampaignBrief(
                product_or_service="Test",
                goal="Test goal",
                budget=1000,
                currency="USD",
                start_date="2026-01-01",
                end_date="2026-03-31",
            )
        )
        # DRAFT -> APPROVED is NOT a valid transition
        assert campaign.status == CampaignStatus.DRAFT

        with patch("backend.agents.coordinator_agent.logger") as mock_logger:
            coordinator._transition(campaign, CampaignStatus.APPROVED)

        # Status is still updated despite being invalid
        assert campaign.status == CampaignStatus.APPROVED
        # Warning was logged
        mock_logger.warning.assert_called_once()
        args, _ = mock_logger.warning.call_args
        assert args[1] == "draft"
        assert args[2] == "approved"


class TestDeclarativePipelineConditions:
    """Verify that StageDefinition conditions gate stages correctly."""

    _BRIEF = CampaignBrief(
        product_or_service="Test",
        goal="Test goal",
        budget=1000,
        currency="USD",
        start_date="2026-01-01",
        end_date="2026-03-31",
    )

    def _get_stage(self, coordinator: CoordinatorAgent, name: str):
        return next(s for s in coordinator._stages if s.name == name)

    def test_stage_registry_has_all_seven_stages(self, store):
        """Coordinator must register exactly the seven expected pipeline stages."""
        coordinator = CoordinatorAgent(store=store)
        names = [s.name for s in coordinator._stages]
        assert names == [
            "strategy",
            "content",
            "channel_planning",
            "analytics",
            "review",
            "content_revision",
            "content_approval",
        ]

    def test_content_revision_skipped_when_review_is_none(self, store):
        """content_revision stage must not run when campaign.review is None."""
        coordinator = CoordinatorAgent(store=store)
        stage = self._get_stage(coordinator, "content_revision")
        campaign = Campaign(brief=self._BRIEF)
        campaign.review = None
        campaign.content = MagicMock()
        assert not stage.condition(campaign)

    def test_content_revision_skipped_when_content_is_none(self, store):
        """content_revision stage must not run when campaign.content is None."""
        coordinator = CoordinatorAgent(store=store)
        stage = self._get_stage(coordinator, "content_revision")
        campaign = Campaign(brief=self._BRIEF)
        campaign.review = MagicMock()
        campaign.content = None
        assert not stage.condition(campaign)

    def test_content_revision_runs_when_both_present(self, store):
        """content_revision stage must run when both review and content are set."""
        coordinator = CoordinatorAgent(store=store)
        stage = self._get_stage(coordinator, "content_revision")
        campaign = Campaign(brief=self._BRIEF)
        campaign.review = MagicMock()
        campaign.content = MagicMock()
        assert stage.condition(campaign)

    def test_content_approval_skipped_when_content_is_none(self, store):
        """content_approval stage must not run when campaign.content is None."""
        coordinator = CoordinatorAgent(store=store)
        stage = self._get_stage(coordinator, "content_approval")
        campaign = Campaign(brief=self._BRIEF)
        campaign.content = None
        assert not stage.condition(campaign)

    def test_content_approval_runs_when_content_present(self, store):
        """content_approval stage must run when campaign.content is set."""
        coordinator = CoordinatorAgent(store=store)
        stage = self._get_stage(coordinator, "content_approval")
        campaign = Campaign(brief=self._BRIEF)
        campaign.content = MagicMock()
        assert stage.condition(campaign)

    def test_early_stages_have_no_condition_guard(self, store):
        """Strategy, content, channel, analytics, and review always run (condition=True)."""
        coordinator = CoordinatorAgent(store=store)
        campaign = Campaign(brief=self._BRIEF)
        for name in ("strategy", "content", "channel_planning", "analytics", "review"):
            stage = self._get_stage(coordinator, name)
            assert stage.condition(campaign), f"{name} stage condition should always be True"


# ---------------------------------------------------------------------------
# Helpers for checkpoint tests
# ---------------------------------------------------------------------------


class _InMemoryCheckpointStore:
    """Dict-backed checkpoint store for unit tests — no database required."""

    def __init__(self) -> None:
        self._checkpoints: dict[str, WorkflowCheckpoint] = {}
        self.calls: list[WorkflowCheckpoint] = []  # ordered record of every save

    async def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        self._checkpoints[checkpoint.campaign_id] = checkpoint
        self.calls.append(checkpoint)

    async def get_checkpoint(self, campaign_id: str) -> Optional[WorkflowCheckpoint]:
        return self._checkpoints.get(campaign_id)

    async def delete_checkpoint(self, campaign_id: str) -> bool:
        if campaign_id in self._checkpoints:
            del self._checkpoints[campaign_id]
            return True
        return False


class _FailingCheckpointStore:
    """Always raises on save — used to verify fail-safe behaviour."""

    async def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        raise RuntimeError("Simulated checkpoint store failure")

    async def get_checkpoint(self, campaign_id: str) -> Optional[WorkflowCheckpoint]:
        return None

    async def delete_checkpoint(self, campaign_id: str) -> bool:
        return False


# ---------------------------------------------------------------------------
# Checkpoint tests
# ---------------------------------------------------------------------------

class TestCoordinatorCheckpoints:
    """Verify that checkpoint writes happen at every stage boundary."""

    @pytest.mark.asyncio
    async def test_checkpoints_written_for_all_stages(self, store, brief, mock_on_event):
        """A checkpoint must be saved at the start of every pipeline stage."""
        campaign = await store.create(brief)
        checkpoint_store = _InMemoryCheckpointStore()

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat_json = AsyncMock(side_effect=_stage_responses())
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(
                store=store,
                on_event=mock_on_event,
                checkpoint_store=checkpoint_store,
            )

            async def _auto_approve():
                await asyncio.sleep(0.3)
                await coordinator.submit_content_approval(
                    ContentApprovalResponse(
                        campaign_id=campaign.id,
                        pieces=[
                            ContentPieceApproval(piece_index=0, approved=True),
                            ContentPieceApproval(piece_index=1, approved=True),
                        ],
                        reject_campaign=False,
                    )
                )

            approve_task = asyncio.create_task(_auto_approve())
            result = await coordinator.run_pipeline(campaign)
            await approve_task

        assert result.status == CampaignStatus.APPROVED

        saved_stages = [cp.current_stage for cp in checkpoint_store.calls]
        for expected_stage in (
            "strategy",
            "content",
            "channel_planning",
            "analytics_setup",
            "review",
            "content_revision",
            "content_approval",
        ):
            assert expected_stage in saved_stages, (
                f"Expected checkpoint for stage '{expected_stage}' but got: {saved_stages}"
            )

    @pytest.mark.asyncio
    async def test_checkpoint_failure_does_not_crash_pipeline(self, store, brief, mock_on_event):
        """A failing checkpoint store must not break the pipeline — checkpoints are additive."""
        campaign = await store.create(brief)

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat_json = AsyncMock(side_effect=_stage_responses())
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(
                store=store,
                on_event=mock_on_event,
                checkpoint_store=_FailingCheckpointStore(),
            )

            async def _auto_approve():
                await asyncio.sleep(0.3)
                await coordinator.submit_content_approval(
                    ContentApprovalResponse(
                        campaign_id=campaign.id,
                        pieces=[
                            ContentPieceApproval(piece_index=0, approved=True),
                            ContentPieceApproval(piece_index=1, approved=True),
                        ],
                        reject_campaign=False,
                    )
                )

            approve_task = asyncio.create_task(_auto_approve())
            result = await coordinator.run_pipeline(campaign)
            await approve_task

        # Pipeline must complete normally despite checkpoint failures
        assert result.status == CampaignStatus.APPROVED

    @pytest.mark.asyncio
    async def test_clarification_wait_checkpoint_has_wait_type(self, store, mock_on_event):
        """Entry to clarification wait must save a checkpoint with CLARIFICATION wait_type."""
        brief = CampaignBrief(
            product_or_service="TestProd",
            goal="Test goal",
            budget=1000,
            currency="USD",
            start_date="2026-01-01",
            end_date="2026-03-31",
        )
        campaign = await store.create(brief)
        checkpoint_store = _InMemoryCheckpointStore()

        clarification_needed = json.dumps({
            "needs_clarification": True,
            "context_summary": "Need more info",
            "questions": [{"text": "What is your target market?", "id": "q1"}],
        })

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat_json = AsyncMock(side_effect=[
                clarification_needed,
                STRATEGY_RESPONSE,
                CONTENT_RESPONSE,
                CHANNEL_RESPONSE,
                ANALYTICS_RESPONSE,
                REVIEW_RESPONSE,
                CONTENT_REVISION_RESPONSE,
            ])
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(
                store=store,
                on_event=mock_on_event,
                checkpoint_store=checkpoint_store,
            )

            async def _submit_clarification():
                await asyncio.sleep(0.1)
                await coordinator.submit_clarification(
                    ClarificationResponse(
                        campaign_id=campaign.id,
                        answers={"q1": "Enterprise software companies"},
                    )
                )

            async def _auto_approve():
                await asyncio.sleep(0.4)
                await coordinator.submit_content_approval(
                    ContentApprovalResponse(
                        campaign_id=campaign.id,
                        pieces=[
                            ContentPieceApproval(piece_index=0, approved=True),
                            ContentPieceApproval(piece_index=1, approved=True),
                        ],
                        reject_campaign=False,
                    )
                )

            clarify_task = asyncio.create_task(_submit_clarification())
            approve_task = asyncio.create_task(_auto_approve())
            await coordinator.run_pipeline(campaign)
            await clarify_task
            await approve_task

        # Find the checkpoint saved when entering the clarification wait
        wait_checkpoints = [
            cp for cp in checkpoint_store.calls
            if cp.wait_type == WorkflowWaitType.CLARIFICATION
        ]
        assert wait_checkpoints, "Expected at least one checkpoint with CLARIFICATION wait_type"
        assert wait_checkpoints[0].current_stage == "clarification"

        # After resolution, wait_type should be cleared
        resolution_checkpoints = [
            cp for cp in checkpoint_store.calls
            if cp.current_stage == "clarification" and cp.wait_type is None
        ]
        assert resolution_checkpoints, (
            "Expected a checkpoint for clarification resolution with wait_type=None"
        )

    @pytest.mark.asyncio
    async def test_content_approval_wait_checkpoint_has_wait_type(self, store, brief, mock_on_event):
        """Entry to content-approval wait must save a checkpoint with CONTENT_APPROVAL wait_type."""
        campaign = await store.create(brief)
        checkpoint_store = _InMemoryCheckpointStore()

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat_json = AsyncMock(side_effect=_stage_responses())
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(
                store=store,
                on_event=mock_on_event,
                checkpoint_store=checkpoint_store,
            )

            async def _auto_approve():
                await asyncio.sleep(0.3)
                await coordinator.submit_content_approval(
                    ContentApprovalResponse(
                        campaign_id=campaign.id,
                        pieces=[
                            ContentPieceApproval(piece_index=0, approved=True),
                            ContentPieceApproval(piece_index=1, approved=True),
                        ],
                        reject_campaign=False,
                    )
                )

            approve_task = asyncio.create_task(_auto_approve())
            result = await coordinator.run_pipeline(campaign)
            await approve_task

        assert result.status == CampaignStatus.APPROVED

        # Checkpoint saved when entering the wait
        wait_checkpoints = [
            cp for cp in checkpoint_store.calls
            if cp.wait_type == WorkflowWaitType.CONTENT_APPROVAL
        ]
        assert wait_checkpoints, "Expected at least one checkpoint with CONTENT_APPROVAL wait_type"
        assert wait_checkpoints[0].current_stage == "content_approval"

        # Checkpoint saved after human responds (wait_type cleared)
        resolution_checkpoints = [
            cp for cp in checkpoint_store.calls
            if cp.current_stage == "content_approval" and cp.wait_type is None
        ]
        assert resolution_checkpoints, (
            "Expected a checkpoint for content_approval resolution with wait_type=None"
        )


# ---------------------------------------------------------------------------
# Timeout tests
# ---------------------------------------------------------------------------

class TestCoordinatorWaitTimeouts:
    """Verify that timed-out human wait states escalate to MANUAL_REVIEW_REQUIRED."""

    @pytest.mark.asyncio
    async def test_clarification_timeout_escalates_to_manual_review(self, store, mock_on_event):
        """When clarification is never answered, the pipeline must transition to
        MANUAL_REVIEW_REQUIRED after the idle timeout elapses."""
        brief = CampaignBrief(
            product_or_service="TestProd",
            goal="Test goal",
            budget=1000,
            currency="USD",
            start_date="2026-01-01",
            end_date="2026-03-31",
        )
        campaign = await store.create(brief)

        clarification_needed = json.dumps({
            "needs_clarification": True,
            "context_summary": "Need more info",
            "questions": [{"text": "What is your target market?", "id": "q1"}],
        })

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat_json = AsyncMock(return_value=clarification_needed)
            mock_get_llm.return_value = mock_llm

            # Use a very short timeout so the test runs fast
            coordinator = CoordinatorAgent(
                store=store,
                on_event=mock_on_event,
                idle_timeout_seconds=0.05,
            )

            # Do NOT submit clarification — let it time out
            result = await coordinator.run_pipeline(campaign)

        assert result.status == CampaignStatus.MANUAL_REVIEW_REQUIRED

    @pytest.mark.asyncio
    async def test_clarification_timeout_emits_wait_timeout_event(self, store, events_log, mock_on_event):
        """A wait_timeout event must be emitted when the clarification gate times out."""
        brief = CampaignBrief(
            product_or_service="TestProd",
            goal="Test goal",
            budget=1000,
            currency="USD",
            start_date="2026-01-01",
            end_date="2026-03-31",
        )
        campaign = await store.create(brief)

        clarification_needed = json.dumps({
            "needs_clarification": True,
            "context_summary": "Need more info",
            "questions": [{"text": "What is your target market?", "id": "q1"}],
        })

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat_json = AsyncMock(return_value=clarification_needed)
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(
                store=store,
                on_event=mock_on_event,
                idle_timeout_seconds=0.05,
            )

            await coordinator.run_pipeline(campaign)

        timeout_events = [e for e in events_log if e["event"] == "wait_timeout"]
        assert timeout_events, "Expected a wait_timeout event"
        assert timeout_events[0]["campaign_id"] == campaign.id
        assert timeout_events[0]["stage"] == "clarification"

    @pytest.mark.asyncio
    async def test_content_approval_timeout_escalates_to_manual_review(self, store, mock_on_event):
        """When content approval is never submitted, the pipeline must transition to
        MANUAL_REVIEW_REQUIRED after the idle timeout elapses."""
        campaign = await store.create(
            CampaignBrief(
                product_or_service="CloudSync — cloud storage for teams",
                goal="Increase enterprise signups by 30% in Q2",
                budget=50000,
                currency="USD",
                start_date="2026-04-01",
                end_date="2026-06-30",
            )
        )

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat_json = AsyncMock(side_effect=_stage_responses())
            mock_get_llm.return_value = mock_llm

            # Use a very short timeout so the test runs fast
            coordinator = CoordinatorAgent(
                store=store,
                on_event=mock_on_event,
                idle_timeout_seconds=0.05,
            )

            # Do NOT submit content approval — let it time out
            result = await coordinator.run_pipeline(campaign)

        assert result.status == CampaignStatus.MANUAL_REVIEW_REQUIRED

    @pytest.mark.asyncio
    async def test_content_approval_timeout_emits_wait_timeout_event(self, store, events_log, mock_on_event):
        """A wait_timeout event must be emitted when the content-approval gate times out."""
        campaign = await store.create(
            CampaignBrief(
                product_or_service="CloudSync — cloud storage for teams",
                goal="Increase enterprise signups by 30% in Q2",
                budget=50000,
                currency="USD",
                start_date="2026-04-01",
                end_date="2026-06-30",
            )
        )

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat_json = AsyncMock(side_effect=_stage_responses())
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(
                store=store,
                on_event=mock_on_event,
                idle_timeout_seconds=0.05,
            )

            await coordinator.run_pipeline(campaign)

        timeout_events = [e for e in events_log if e["event"] == "wait_timeout"]
        assert timeout_events, "Expected a wait_timeout event"
        assert timeout_events[0]["campaign_id"] == campaign.id
        assert timeout_events[0]["stage"] == "content_approval"

    @pytest.mark.asyncio
    async def test_checkpoint_stores_expiry_on_wait_entry(self, store, mock_on_event):
        """Checkpoints saved at wait entry must carry wait_started_at and expires_at."""
        campaign = await store.create(
            CampaignBrief(
                product_or_service="CloudSync",
                goal="Increase signups",
                budget=50000,
                currency="USD",
                start_date="2026-04-01",
                end_date="2026-06-30",
            )
        )
        checkpoint_store = _InMemoryCheckpointStore()

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat_json = AsyncMock(side_effect=_stage_responses())
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(
                store=store,
                on_event=mock_on_event,
                checkpoint_store=checkpoint_store,
                idle_timeout_seconds=0.05,
            )

            # Don't approve — let the content-approval gate time out so we can
            # inspect the checkpoint saved at wait entry.
            await coordinator.run_pipeline(campaign)

        wait_checkpoints = [
            cp for cp in checkpoint_store.calls
            if cp.wait_type == WorkflowWaitType.CONTENT_APPROVAL
        ]
        assert wait_checkpoints, "Expected a checkpoint with CONTENT_APPROVAL wait_type"
        cp = wait_checkpoints[0]
        assert cp.wait_started_at is not None, "wait_started_at must be set on wait entry"
        assert cp.expires_at is not None, "expires_at must be set on wait entry"
        assert cp.expires_at > cp.wait_started_at, "expires_at must be after wait_started_at"

class TestCoordinatorResume:
    """Verify resume_pipeline idempotency and checkpoint-based recovery."""

    @pytest.fixture
    def brief(self):
        return CampaignBrief(
            product_or_service="CloudSync — cloud storage for teams",
            goal="Increase enterprise signups by 30% in Q2",
            budget=50000,
            currency="USD",
            start_date="2026-04-01",
            end_date="2026-06-30",
        )

    @pytest.mark.asyncio
    async def test_resume_with_existing_strategy_skips_strategy_stage(
        self, store, brief, mock_on_event
    ):
        """A campaign with strategy already set must skip the strategy stage on resume.

        Only content, channel, analytics, review, content_revision, and
        content_approval should execute — strategy must not be re-run.
        """
        campaign = await store.create(brief)
        from backend.models.campaign import CampaignStrategy, TargetAudience

        # Pre-populate strategy so the stage should be skipped on resume
        campaign.strategy = CampaignStrategy(
            objectives=["Increase signups"],
            target_audience=TargetAudience(
                demographics="25-45",
                psychographics="Productivity-focused",
                pain_points=["Data silos"],
                personas=["IT Manager Maria"],
            ),
            value_proposition="Seamless collaboration",
            positioning="Enterprise-grade simplicity",
            key_messages=["Work anywhere"],
            competitive_landscape="Dropbox, Box",
            constraints="$50K budget",
        )
        campaign.status = CampaignStatus.STRATEGY
        await store.update(campaign)

        checkpoint_store = _InMemoryCheckpointStore()
        from datetime import datetime
        checkpoint_store._checkpoints[campaign.id] = WorkflowCheckpoint(
            campaign_id=campaign.id,
            current_stage="strategy",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        llm_call_count = 0

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()

            original_side_effect = [
                CONTENT_RESPONSE,
                CHANNEL_RESPONSE,
                ANALYTICS_RESPONSE,
                REVIEW_RESPONSE,
                CONTENT_REVISION_RESPONSE,
            ]

            def count_and_return(messages, **kwargs):
                nonlocal llm_call_count
                llm_call_count += 1
                return original_side_effect[llm_call_count - 1]

            mock_llm.chat_json = AsyncMock(side_effect=original_side_effect)
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(
                store=store,
                on_event=mock_on_event,
                checkpoint_store=checkpoint_store,
            )

            async def _auto_approve():
                await asyncio.sleep(0.3)
                await coordinator.submit_content_approval(
                    ContentApprovalResponse(
                        campaign_id=campaign.id,
                        pieces=[
                            ContentPieceApproval(piece_index=0, approved=True),
                            ContentPieceApproval(piece_index=1, approved=True),
                        ],
                        reject_campaign=False,
                    )
                )

            approve_task = asyncio.create_task(_auto_approve())
            result = await coordinator.resume_pipeline(campaign.id)
            await approve_task

        assert result.status == CampaignStatus.APPROVED

        # Strategy was pre-populated and should not have been overwritten
        assert result.strategy is not None
        assert result.strategy.objectives == ["Increase signups"]

        # All later stages must have run
        assert result.content is not None
        assert result.channel_plan is not None
        assert result.analytics_plan is not None
        assert result.review is not None

        # Strategy LLM call must not have been made — only 5 calls (content,
        # channel, analytics, review, content_revision)
        assert mock_llm.chat_json.call_count == 5

    @pytest.mark.asyncio
    async def test_resume_clarification_with_existing_answers(
        self, store, mock_on_event
    ):
        """A campaign stuck in clarification with answers already present must
        skip the clarification wait and continue to run all pipeline stages."""
        clarification_brief = CampaignBrief(
            product_or_service="TestProd",
            goal="Test goal",
            budget=1000,
            currency="USD",
            start_date="2026-01-01",
            end_date="2026-03-31",
        )
        campaign = await store.create(clarification_brief)

        # Simulate: pipeline paused at clarification, answers already submitted
        campaign.status = CampaignStatus.CLARIFICATION
        campaign.clarification_questions = [{"id": "q1", "text": "What is your target market?"}]
        campaign.clarification_answers = {"q1": "Enterprise software companies"}
        await store.update(campaign)

        checkpoint_store = _InMemoryCheckpointStore()
        from datetime import datetime
        checkpoint_store._checkpoints[campaign.id] = WorkflowCheckpoint(
            campaign_id=campaign.id,
            current_stage="clarification",
            wait_type=WorkflowWaitType.CLARIFICATION,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            # gather_clarifications + all 6 pipeline stages
            mock_llm.chat_json = AsyncMock(side_effect=[
                CLARIFICATION_RESPONSE,   # gather_clarifications (clarification already answered)
                STRATEGY_RESPONSE,
                CONTENT_RESPONSE,
                CHANNEL_RESPONSE,
                ANALYTICS_RESPONSE,
                REVIEW_RESPONSE,
                CONTENT_REVISION_RESPONSE,
            ])
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(
                store=store,
                on_event=mock_on_event,
                checkpoint_store=checkpoint_store,
            )

            async def _auto_approve():
                await asyncio.sleep(0.4)
                await coordinator.submit_content_approval(
                    ContentApprovalResponse(
                        campaign_id=campaign.id,
                        pieces=[
                            ContentPieceApproval(piece_index=0, approved=True),
                            ContentPieceApproval(piece_index=1, approved=True),
                        ],
                        reject_campaign=False,
                    )
                )

            approve_task = asyncio.create_task(_auto_approve())
            result = await coordinator.resume_pipeline(campaign.id)
            await approve_task

        # Pipeline must complete successfully
        assert result.status == CampaignStatus.APPROVED
        assert result.strategy is not None
        assert result.content is not None
        assert result.channel_plan is not None
        assert result.analytics_plan is not None
        assert result.review is not None

    @pytest.mark.asyncio
    async def test_resume_with_no_checkpoint_starts_fresh(self, store, brief, mock_on_event):
        """When no checkpoint exists, resume_pipeline must run a full fresh pipeline."""
        campaign = await store.create(brief)

        # No checkpoint saved for this campaign
        checkpoint_store = _InMemoryCheckpointStore()

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat_json = AsyncMock(side_effect=_stage_responses())
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(
                store=store,
                on_event=mock_on_event,
                checkpoint_store=checkpoint_store,
            )

            async def _auto_approve():
                await asyncio.sleep(0.3)
                await coordinator.submit_content_approval(
                    ContentApprovalResponse(
                        campaign_id=campaign.id,
                        pieces=[
                            ContentPieceApproval(piece_index=0, approved=True),
                            ContentPieceApproval(piece_index=1, approved=True),
                        ],
                        reject_campaign=False,
                    )
                )

            approve_task = asyncio.create_task(_auto_approve())
            result = await coordinator.resume_pipeline(campaign.id)
            await approve_task

        assert result.status == CampaignStatus.APPROVED
        assert result.strategy is not None
        assert result.content is not None
        assert result.channel_plan is not None
        assert result.analytics_plan is not None
        assert result.review is not None

    @pytest.mark.asyncio
    async def test_resume_fully_completed_campaign_not_rerun(
        self, store, brief, mock_on_event
    ):
        """A fully approved campaign must not trigger any agent stage on resume."""
        from backend.models.campaign import (
            CampaignStrategy,
            CampaignContent,
            ChannelPlan,
            AnalyticsPlan,
            ReviewFeedback,
            TargetAudience,
            ChannelType,
        )
        from backend.models.campaign import ContentPiece, ChannelRecommendation, KPI

        campaign = await store.create(brief)

        # Populate all stages as if the pipeline completed normally
        campaign.strategy = CampaignStrategy(
            objectives=["Increase signups"],
            target_audience=TargetAudience(),
            value_proposition="Seamless collaboration",
            positioning="Enterprise-grade",
            key_messages=["Work anywhere"],
            competitive_landscape="Dropbox",
            constraints="$50K",
        )
        campaign.content = CampaignContent(
            theme="Unleash",
            tone_of_voice="Professional",
            pieces=[
                ContentPiece(
                    content_type="headline",
                    channel="email",
                    content="Sync Without Limits",
                    approval_status=ContentApprovalStatus.APPROVED,
                ),
            ],
        )
        campaign.channel_plan = ChannelPlan(
            total_budget=50000,
            currency="USD",
            recommendations=[
                ChannelRecommendation(
                    channel=ChannelType.EMAIL,
                    rationale="High ROI",
                    budget_pct=25,
                    timing="Week 1-12",
                    tactics=["Drip"],
                ),
            ],
            timeline_summary="12-week plan",
        )
        campaign.analytics_plan = AnalyticsPlan(
            kpis=[KPI(name="Signup Rate", target_value="5%")],
            tracking_tools=["GA4"],
            reporting_cadence="weekly",
            attribution_model="multi-touch",
            success_criteria="30% increase",
        )
        campaign.review = ReviewFeedback(
            approved=True,
            issues=[],
            suggestions=[],
            brand_consistency_score=9.0,
        )
        campaign.content_revision_count = 1
        campaign.status = CampaignStatus.APPROVED
        await store.update(campaign)

        checkpoint_store = _InMemoryCheckpointStore()
        from datetime import datetime
        checkpoint_store._checkpoints[campaign.id] = WorkflowCheckpoint(
            campaign_id=campaign.id,
            current_stage="content_approval",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat_json = AsyncMock()
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(
                store=store,
                on_event=mock_on_event,
                checkpoint_store=checkpoint_store,
            )

            result = await coordinator.resume_pipeline(campaign.id)

        # Campaign remains approved, no stages re-run
        assert result.status == CampaignStatus.APPROVED

        # No LLM calls should have been made
        mock_llm.chat_json.assert_not_called()

        # Original strategy is unchanged
        assert result.strategy.objectives == ["Increase signups"]

    @pytest.mark.asyncio
    async def test_resume_raises_for_unknown_campaign(self, store):
        """resume_pipeline must raise ValueError when the campaign does not exist."""
        coordinator = CoordinatorAgent(store=store)
        with pytest.raises(ValueError, match="not found"):
            await coordinator.resume_pipeline("nonexistent-id")
