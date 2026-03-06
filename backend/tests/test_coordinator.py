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
from unittest.mock import AsyncMock, MagicMock, patch

from backend.agents.coordinator_agent import CoordinatorAgent
from backend.models.campaign import Campaign, CampaignBrief, CampaignStatus, ContentApprovalStatus
from backend.models.messages import ClarificationResponse, ContentApprovalResponse, ContentPieceApproval
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
