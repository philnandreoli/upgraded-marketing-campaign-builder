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
from backend.models.messages import ContentApprovalResponse, ContentPieceApproval
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
        timeline="3 months",
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
    async def test_pipeline_handles_stage_failure(self, store, brief, events_log, mock_on_event):
        """If an agent fails, the pipeline should continue (graceful degradation)."""
        campaign = await store.create(brief)

        with patch("backend.agents.base_agent.get_llm_service") as mock_get_llm:
            mock_llm = MagicMock()
            # Clarification skipped, strategy succeeds, then all others fail
            mock_llm.chat_json = AsyncMock(
                side_effect=[
                    CLARIFICATION_RESPONSE,
                    STRATEGY_RESPONSE,
                    Exception("Content LLM Error"),
                    Exception("Channel LLM Error"),
                    Exception("Analytics LLM Error"),
                    Exception("Review LLM Error"),
                ]
            )
            mock_get_llm.return_value = mock_llm

            coordinator = CoordinatorAgent(store=store, on_event=mock_on_event)
            result = await coordinator.run_pipeline(campaign)

        # Strategy should be populated
        assert result.strategy is not None
        # Other sections should be None since agents failed
        assert result.content is None
        assert result.channel_plan is None
        assert result.analytics_plan is None

        # Stage errors emitted
        event_names = [e["event"] for e in events_log]
        assert "stage_error" in event_names


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
