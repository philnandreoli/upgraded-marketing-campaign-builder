"""
Tests for individual agents — each agent's prompt construction and response parsing.

LLM is fully mocked; these tests verify that:
- System prompts are well-formed
- User prompts include brief/strategy data
- parse_response handles valid JSON
- parse_response handles malformed JSON gracefully
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.agents.strategy_agent import StrategyAgent
from backend.agents.content_creator_agent import ContentCreatorAgent
from backend.agents.channel_planner_agent import ChannelPlannerAgent
from backend.agents.analytics_agent import AnalyticsAgent
from backend.agents.review_qa_agent import ReviewQAAgent
from backend.models.messages import AgentTask, AgentType


# ---- Fixtures ----

@pytest.fixture
def mock_llm():
    svc = MagicMock()
    svc.chat = AsyncMock()
    svc.chat_json = AsyncMock()
    return svc


def _make_task(agent_type: AgentType, campaign_id: str = "c1") -> AgentTask:
    return AgentTask(
        task_id="t1",
        agent_type=agent_type,
        campaign_id=campaign_id,
        instruction="",
    )


SAMPLE_BRIEF = {
    "product_or_service": "CloudSync",
    "goal": "Increase enterprise signups by 30%",
    "budget": 50000,
    "currency": "USD",
    "start_date": "2026-04-01",
    "end_date": "2026-06-30",
    "additional_context": "Focus on mid-market",
    "selected_channels": [],
}

# Variant with selected channels
SAMPLE_BRIEF_WITH_CHANNELS = {
    **SAMPLE_BRIEF,
    "selected_channels": ["email", "paid_ads", "seo"],
}

SAMPLE_CAMPAIGN_DATA = {
    "brief": SAMPLE_BRIEF,
    "strategy": {
        "objectives": ["Increase signups by 30%"],
        "target_audience": {
            "demographics": "25-45 tech professionals",
            "psychographics": "Productivity-focused",
            "pain_points": ["Data silos"],
            "personas": ["IT Manager Maria"],
        },
        "value_proposition": "Seamless cloud collaboration",
        "positioning": "Enterprise-grade simplicity",
        "key_messages": ["Work anywhere", "Bank-level security"],
    },
    "content": {
        "theme": "Unleash Collaboration",
        "tone_of_voice": "Professional yet approachable",
        "pieces": [
            {"content_type": "headline", "channel": "email", "content": "Sync Without Limits", "variant": "A"},
        ],
    },
    "channel_plan": {
        "total_budget": 50000,
        "currency": "USD",
        "recommendations": [
            {"channel": "email", "rationale": "High ROI", "budget_pct": 30, "timing": "Week 1-12"},
            {"channel": "paid_ads", "rationale": "Quick reach", "budget_pct": 40, "timing": "Week 1-8"},
        ],
    },
    "analytics_plan": {
        "kpis": [{"name": "Signup Rate", "target_value": "5%", "measurement_method": "GA4"}],
        "tracking_tools": ["Google Analytics 4"],
        "reporting_cadence": "weekly",
        "attribution_model": "multi-touch",
        "success_criteria": "30% increase in signups",
    },
}

SAMPLE_CAMPAIGN_DATA_WITH_CHANNELS = {
    **SAMPLE_CAMPAIGN_DATA,
    "brief": SAMPLE_BRIEF_WITH_CHANNELS,
}


# ---- Strategy Agent ----

class TestStrategyAgent:
    def test_system_prompt_not_empty(self, mock_llm):
        agent = StrategyAgent(llm_service=mock_llm)
        prompt = agent.system_prompt()
        assert "Marketing Strategist" in prompt
        assert "JSON" in prompt

    def test_build_user_prompt_includes_brief(self, mock_llm):
        agent = StrategyAgent(llm_service=mock_llm)
        task = _make_task(AgentType.STRATEGY)
        prompt = agent.build_user_prompt(task, SAMPLE_CAMPAIGN_DATA)
        assert "CloudSync" in prompt
        assert "50,000" in prompt
        assert "2026-04-01" in prompt
        assert "2026-06-30" in prompt

    def test_parse_valid_response(self, mock_llm):
        agent = StrategyAgent(llm_service=mock_llm)
        task = _make_task(AgentType.STRATEGY)
        raw = json.dumps({
            "objectives": ["Grow 30%"],
            "target_audience": {"demographics": "25-45"},
            "value_proposition": "Best storage",
            "positioning": "Enterprise leader",
            "key_messages": ["Fast", "Secure"],
        })
        result = agent.parse_response(raw, task)
        assert "objectives" in result
        assert len(result["objectives"]) == 1

    def test_parse_response_adds_defaults(self, mock_llm):
        agent = StrategyAgent(llm_service=mock_llm)
        task = _make_task(AgentType.STRATEGY)
        result = agent.parse_response("{}", task)
        assert "objectives" in result
        assert "key_messages" in result

    def test_parse_strips_markdown_fences(self, mock_llm):
        agent = StrategyAgent(llm_service=mock_llm)
        task = _make_task(AgentType.STRATEGY)
        raw = '```json\n{"objectives": ["Test"]}\n```'
        result = agent.parse_response(raw, task)
        assert result["objectives"] == ["Test"]

    @pytest.mark.asyncio
    async def test_run_success(self, mock_llm):
        mock_llm.chat_json = AsyncMock(return_value=json.dumps({
            "objectives": ["Grow"],
            "target_audience": {},
            "value_proposition": "VP",
            "positioning": "P",
            "key_messages": ["M"],
        }))
        agent = StrategyAgent(llm_service=mock_llm)
        task = _make_task(AgentType.STRATEGY)
        result = await agent.run(task, SAMPLE_CAMPAIGN_DATA)
        assert result.success is True
        assert "objectives" in result.output

    @pytest.mark.asyncio
    async def test_run_llm_failure(self, mock_llm):
        mock_llm.chat_json = AsyncMock(side_effect=Exception("API Error"))
        agent = StrategyAgent(llm_service=mock_llm)
        task = _make_task(AgentType.STRATEGY)
        result = await agent.run(task, SAMPLE_CAMPAIGN_DATA)
        assert result.success is False
        assert "API Error" in result.error

    def test_prompt_includes_selected_channels(self, mock_llm):
        agent = StrategyAgent(llm_service=mock_llm)
        task = _make_task(AgentType.STRATEGY)
        prompt = agent.build_user_prompt(task, SAMPLE_CAMPAIGN_DATA_WITH_CHANNELS)
        assert "Selected Channels" in prompt
        assert "Email" in prompt
        assert "Paid Ads" in prompt
        assert "Seo" in prompt

    def test_prompt_omits_channels_when_empty(self, mock_llm):
        agent = StrategyAgent(llm_service=mock_llm)
        task = _make_task(AgentType.STRATEGY)
        prompt = agent.build_user_prompt(task, SAMPLE_CAMPAIGN_DATA)
        assert "Selected Channels" not in prompt


# ---- Content Creator Agent ----

class TestContentCreatorAgent:
    def test_system_prompt(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        assert "Copywriter" in agent.system_prompt()

    def test_build_prompt_includes_strategy(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        prompt = agent.build_user_prompt(task, SAMPLE_CAMPAIGN_DATA)
        assert "Seamless cloud collaboration" in prompt

    def test_prompt_includes_selected_channels(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        prompt = agent.build_user_prompt(task, SAMPLE_CAMPAIGN_DATA_WITH_CHANNELS)
        assert "Selected Channels" in prompt
        assert "Only create content for the channels listed" in prompt

    def test_prompt_omits_channels_when_empty(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        prompt = agent.build_user_prompt(task, SAMPLE_CAMPAIGN_DATA)
        assert "Selected Channels" not in prompt
        assert "Work anywhere" in prompt

    def test_parse_response(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        raw = json.dumps({
            "theme": "Unleash",
            "tone_of_voice": "Bold",
            "pieces": [{"content_type": "headline", "content": "Go Cloud"}],
        })
        result = agent.parse_response(raw, task)
        assert len(result["pieces"]) == 1

    def test_parse_response_drops_blank_pieces(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        raw = json.dumps({
            "theme": "Unleash",
            "tone_of_voice": "Bold",
            "pieces": [
                {"content_type": "headline", "content": "   "},
                {"content_type": "", "content": "Valid text but missing type"},
                {"content_type": "social_post", "channel": "social_media", "content": "Post copy"},
            ],
        })
        result = agent.parse_response(raw, task)
        assert len(result["pieces"]) == 1
        assert result["pieces"][0]["content_type"] == "social_post"
        assert result["pieces"][0]["content"] == "Post copy"

    @pytest.mark.asyncio
    async def test_run_success(self, mock_llm):
        mock_llm.chat_json = AsyncMock(return_value=json.dumps({
            "theme": "T",
            "tone_of_voice": "Bold",
            "pieces": [],
        }))
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        result = await agent.run(task, SAMPLE_CAMPAIGN_DATA)
        assert result.success is True


class TestContentCreatorRevision:
    def test_revision_system_prompt(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        prompt = agent.revision_system_prompt()
        assert "improve" in prompt.lower() or "revise" in prompt.lower()

    def test_build_revision_prompt_includes_original_content(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        data = {
            **SAMPLE_CAMPAIGN_DATA,
            "content": {
                "theme": "Old Theme",
                "tone_of_voice": "Formal",
                "pieces": [
                    {"content_type": "headline", "channel": "email", "content": "Old Headline", "variant": "A"},
                ],
            },
            "review": {
                "approved": False,
                "issues": ["Tone is too formal"],
                "suggestions": ["Make it more casual"],
                "brand_consistency_score": 5.0,
                "review_summary": "Needs work",
            },
        }
        prompt = agent.build_revision_prompt(task, data)
        assert "Old Headline" in prompt
        assert "Tone is too formal" in prompt
        assert "Make it more casual" in prompt

    def test_build_revision_prompt_handles_missing_review(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        data = {
            **SAMPLE_CAMPAIGN_DATA,
            "review": None,
        }
        # Should not crash even when review data is missing
        prompt = agent.build_revision_prompt(task, data)
        assert "Sync Without Limits" in prompt

    def test_build_piece_revision_prompt_includes_piece(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        data = {
            **SAMPLE_CAMPAIGN_DATA,
            "review": {
                "approved": False,
                "issues": ["Missing CTA"],
                "suggestions": ["Add urgency"],
                "brand_consistency_score": 6.0,
                "review_summary": "Needs work",
            },
        }
        rejected_pieces = [
            {
                "content_type": "headline",
                "channel": "email",
                "content": "Sync Without Limits",
                "variant": "A",
                "human_notes": "Make it punchier",
            },
        ]
        prompt = agent.build_piece_revision_prompt(task, data, rejected_pieces)
        assert "Sync Without Limits" in prompt
        assert "Make it punchier" in prompt


# ---- Channel Planner Agent ----

class TestChannelPlannerAgent:
    def test_system_prompt(self, mock_llm):
        agent = ChannelPlannerAgent(llm_service=mock_llm)
        assert "Channel Strategist" in agent.system_prompt()

    def test_build_prompt_includes_budget(self, mock_llm):
        agent = ChannelPlannerAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CHANNEL_PLANNER)
        prompt = agent.build_user_prompt(task, SAMPLE_CAMPAIGN_DATA)
        assert "50,000" in prompt

    def test_parse_response(self, mock_llm):
        agent = ChannelPlannerAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CHANNEL_PLANNER)
        raw = json.dumps({
            "total_budget": 50000,
            "currency": "USD",
            "recommendations": [
                {"channel": "email", "budget_pct": 30, "rationale": "ROI"},
            ],
        })
        result = agent.parse_response(raw, task)
        assert len(result["recommendations"]) == 1

    def test_prompt_includes_selected_channels(self, mock_llm):
        agent = ChannelPlannerAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CHANNEL_PLANNER)
        prompt = agent.build_user_prompt(task, SAMPLE_CAMPAIGN_DATA_WITH_CHANNELS)
        assert "Selected Channels" in prompt
        assert "Only include recommendations for the channels listed" in prompt

    def test_prompt_omits_channels_when_empty(self, mock_llm):
        agent = ChannelPlannerAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CHANNEL_PLANNER)
        prompt = agent.build_user_prompt(task, SAMPLE_CAMPAIGN_DATA)
        assert "Selected Channels" not in prompt


# ---- Analytics Agent ----

class TestAnalyticsAgent:
    def test_system_prompt(self, mock_llm):
        agent = AnalyticsAgent(llm_service=mock_llm)
        assert "Analytics" in agent.system_prompt()

    def test_build_prompt_includes_channels(self, mock_llm):
        agent = AnalyticsAgent(llm_service=mock_llm)
        task = _make_task(AgentType.ANALYTICS)
        prompt = agent.build_user_prompt(task, SAMPLE_CAMPAIGN_DATA)
        assert "email" in prompt

    def test_parse_response(self, mock_llm):
        agent = AnalyticsAgent(llm_service=mock_llm)
        task = _make_task(AgentType.ANALYTICS)
        raw = json.dumps({
            "kpis": [{"name": "CTR", "target_value": "3%"}],
            "tracking_tools": ["GA4"],
            "reporting_cadence": "weekly",
        })
        result = agent.parse_response(raw, task)
        assert len(result["kpis"]) == 1

    def test_prompt_includes_selected_channels(self, mock_llm):
        agent = AnalyticsAgent(llm_service=mock_llm)
        task = _make_task(AgentType.ANALYTICS)
        prompt = agent.build_user_prompt(task, SAMPLE_CAMPAIGN_DATA_WITH_CHANNELS)
        assert "Selected Channels" in prompt
        assert "Focus KPIs" in prompt

    def test_prompt_omits_channels_when_empty(self, mock_llm):
        agent = AnalyticsAgent(llm_service=mock_llm)
        task = _make_task(AgentType.ANALYTICS)
        prompt = agent.build_user_prompt(task, SAMPLE_CAMPAIGN_DATA)
        assert "Selected Channels" not in prompt


# ---- Review QA Agent ----

class TestReviewQAAgent:
    def test_system_prompt(self, mock_llm):
        agent = ReviewQAAgent(llm_service=mock_llm)
        assert "Quality Assurance" in agent.system_prompt()

    def test_requires_human_approval_flag(self, mock_llm):
        agent = ReviewQAAgent(llm_service=mock_llm)
        assert agent.requires_human_approval is True

    def test_build_prompt_includes_all_sections(self, mock_llm):
        agent = ReviewQAAgent(llm_service=mock_llm)
        task = _make_task(AgentType.REVIEW_QA)
        prompt = agent.build_user_prompt(task, SAMPLE_CAMPAIGN_DATA)
        assert "CloudSync" in prompt
        assert "Strategy" in prompt
        assert "Content" in prompt
        assert "Channel Plan" in prompt
        assert "Analytics" in prompt

    def test_parse_response_sets_human_approval(self, mock_llm):
        agent = ReviewQAAgent(llm_service=mock_llm)
        task = _make_task(AgentType.REVIEW_QA)
        raw = json.dumps({
            "approved": True,
            "issues": [],
            "suggestions": ["Add video content"],
            "brand_consistency_score": 8.5,
            "review_summary": "Looks great",
        })
        result = agent.parse_response(raw, task)
        assert result["requires_human_approval"] is True
        assert result["approved"] is True
        assert result["brand_consistency_score"] == 8.5

    @pytest.mark.asyncio
    async def test_run_success(self, mock_llm):
        mock_llm.chat_json = AsyncMock(return_value=json.dumps({
            "approved": False,
            "issues": ["Tone inconsistency"],
            "suggestions": ["Align tone"],
            "brand_consistency_score": 6.0,
            "review_summary": "Needs work",
        }))
        agent = ReviewQAAgent(llm_service=mock_llm)
        task = _make_task(AgentType.REVIEW_QA)
        result = await agent.run(task, SAMPLE_CAMPAIGN_DATA)
        assert result.success is True
        assert result.output["approved"] is False

    def test_prompt_includes_selected_channels(self, mock_llm):
        agent = ReviewQAAgent(llm_service=mock_llm)
        task = _make_task(AgentType.REVIEW_QA)
        prompt = agent.build_user_prompt(task, SAMPLE_CAMPAIGN_DATA_WITH_CHANNELS)
        assert "Selected Channels" in prompt
        assert "non-selected channels" in prompt

    def test_prompt_omits_channels_when_empty(self, mock_llm):
        agent = ReviewQAAgent(llm_service=mock_llm)
        task = _make_task(AgentType.REVIEW_QA)
        prompt = agent.build_user_prompt(task, SAMPLE_CAMPAIGN_DATA)
        assert "Selected Channels" not in prompt
