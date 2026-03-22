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
from types import SimpleNamespace

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

# Variant with social media channel and specific platforms
SAMPLE_BRIEF_WITH_SOCIAL_PLATFORMS = {
    **SAMPLE_BRIEF,
    "selected_channels": ["social_media"],
    "social_media_platforms": ["instagram", "facebook", "linkedin"],
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

SAMPLE_CAMPAIGN_DATA_WITH_SOCIAL_PLATFORMS = {
    **SAMPLE_CAMPAIGN_DATA,
    "brief": SAMPLE_BRIEF_WITH_SOCIAL_PLATFORMS,
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

    def test_prompt_includes_image_brief_instructions_when_both_flags_enabled(self, mock_llm, monkeypatch):
        monkeypatch.setattr(
            "backend.orchestration.content_creator_agent.get_settings",
            lambda: SimpleNamespace(image_generation=SimpleNamespace(enabled=True)),
        )
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        data = {
            **SAMPLE_CAMPAIGN_DATA,
            "brief": {**SAMPLE_CAMPAIGN_DATA["brief"], "generate_images": True},
        }
        prompt = agent.build_user_prompt(task, data)
        assert "IMAGE BRIEF INSTRUCTIONS" in prompt

    def test_prompt_omits_image_brief_instructions_when_platform_disabled(self, mock_llm, monkeypatch):
        monkeypatch.setattr(
            "backend.orchestration.content_creator_agent.get_settings",
            lambda: SimpleNamespace(image_generation=SimpleNamespace(enabled=False)),
        )
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        data = {
            **SAMPLE_CAMPAIGN_DATA,
            "brief": {**SAMPLE_CAMPAIGN_DATA["brief"], "generate_images": True},
        }
        prompt = agent.build_user_prompt(task, data)
        assert "IMAGE BRIEF INSTRUCTIONS" not in prompt

    def test_prompt_omits_image_brief_instructions_when_user_opt_out(self, mock_llm, monkeypatch):
        monkeypatch.setattr(
            "backend.orchestration.content_creator_agent.get_settings",
            lambda: SimpleNamespace(image_generation=SimpleNamespace(enabled=True)),
        )
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        data = {
            **SAMPLE_CAMPAIGN_DATA,
            "brief": {**SAMPLE_CAMPAIGN_DATA["brief"], "generate_images": False},
        }
        prompt = agent.build_user_prompt(task, data)
        assert "IMAGE BRIEF INSTRUCTIONS" not in prompt

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

    def test_parse_response_keeps_valid_image_brief(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        raw = json.dumps({
            "theme": "Unleash",
            "tone_of_voice": "Bold",
            "pieces": [
                {
                    "content_type": "social_post",
                    "channel": "social_media",
                    "content": "Launch day is here.",
                    "image_brief": {
                        "prompt": "Product launch celebration with confetti and laptop, modern brand colors",
                        "creative_brief": "Energetic product launch hero visual",
                        "suggested_dimensions": "1024x1024",
                    },
                },
            ],
        })
        result = agent.parse_response(raw, task)
        assert result["pieces"][0]["image_brief"]["prompt"].startswith("Product launch")

    def test_parse_response_drops_invalid_image_brief_without_prompt(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        raw = json.dumps({
            "theme": "Unleash",
            "tone_of_voice": "Bold",
            "pieces": [
                {
                    "content_type": "social_post",
                    "channel": "social_media",
                    "content": "Launch day is here.",
                    "image_brief": {
                        "prompt": "   ",
                        "creative_brief": "ignored because prompt blank",
                    },
                },
            ],
        })
        result = agent.parse_response(raw, task)
        assert result["pieces"][0]["image_brief"] is None

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

    def test_parse_response_merges_headline_cta_pairs(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        raw = json.dumps({
            "theme": "Unleash",
            "tone_of_voice": "Bold",
            "pieces": [
                {"content_type": "headline", "channel": "email", "content": "Go Cloud Now", "variant": "A", "notes": "punchy"},
                {"content_type": "cta", "channel": "email", "content": "Start Free Trial", "variant": "A", "notes": "urgency"},
            ],
        })
        result = agent.parse_response(raw, task)
        assert len(result["pieces"]) == 1
        piece = result["pieces"][0]
        assert piece["content_type"] == "headline_cta"
        assert "Go Cloud Now" in piece["content"]
        assert "Start Free Trial" in piece["content"]
        assert "\n---\n" in piece["content"]
        assert "punchy" in piece["notes"]
        assert "urgency" in piece["notes"]

    def test_parse_response_merges_multiple_headline_cta_variants(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        raw = json.dumps({
            "theme": "Unleash",
            "tone_of_voice": "Bold",
            "pieces": [
                {"content_type": "headline", "channel": "email", "content": "Headline A", "variant": "A", "notes": ""},
                {"content_type": "cta", "channel": "email", "content": "CTA A", "variant": "A", "notes": ""},
                {"content_type": "headline", "channel": "email", "content": "Headline B", "variant": "B", "notes": ""},
                {"content_type": "cta", "channel": "email", "content": "CTA B", "variant": "B", "notes": ""},
                {"content_type": "social_post", "channel": "social_media", "content": "Post copy", "variant": "A", "notes": ""},
            ],
        })
        result = agent.parse_response(raw, task)
        headline_cta_pieces = [p for p in result["pieces"] if p["content_type"] == "headline_cta"]
        assert len(headline_cta_pieces) == 2
        variants = {p["variant"] for p in headline_cta_pieces}
        assert variants == {"A", "B"}
        social_pieces = [p for p in result["pieces"] if p["content_type"] == "social_post"]
        assert len(social_pieces) == 1

    def test_parse_response_leaves_standalone_headline_or_cta_unchanged(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        # headline with no matching cta for same (channel, variant)
        raw = json.dumps({
            "theme": "T",
            "tone_of_voice": "Bold",
            "pieces": [
                {"content_type": "headline", "channel": "email", "content": "Only a headline", "variant": "A", "notes": ""},
            ],
        })
        result = agent.parse_response(raw, task)
        assert len(result["pieces"]) == 1
        assert result["pieces"][0]["content_type"] == "headline"

    def test_parse_response_passes_through_headline_cta_natively(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        raw = json.dumps({
            "theme": "T",
            "tone_of_voice": "Bold",
            "pieces": [
                {
                    "content_type": "headline_cta",
                    "channel": "email",
                    "content": "Go Cloud Now\n---\nStart Free Trial",
                    "variant": "A",
                    "notes": "combined",
                },
            ],
        })
        result = agent.parse_response(raw, task)
        assert len(result["pieces"]) == 1
        assert result["pieces"][0]["content_type"] == "headline_cta"
        assert result["pieces"][0]["content"] == "Go Cloud Now\n---\nStart Free Trial"

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

    def test_revision_prompt_includes_image_brief_instructions_when_both_flags_enabled(self, mock_llm, monkeypatch):
        monkeypatch.setattr(
            "backend.orchestration.content_creator_agent.get_settings",
            lambda: SimpleNamespace(image_generation=SimpleNamespace(enabled=True)),
        )
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        data = {
            **SAMPLE_CAMPAIGN_DATA,
            "brief": {**SAMPLE_CAMPAIGN_DATA["brief"], "generate_images": True},
        }
        prompt = agent.build_revision_prompt(task, data)
        assert "IMAGE BRIEF INSTRUCTIONS" in prompt

    def test_revision_prompt_omits_image_brief_instructions_when_user_opt_out(self, mock_llm, monkeypatch):
        monkeypatch.setattr(
            "backend.orchestration.content_creator_agent.get_settings",
            lambda: SimpleNamespace(image_generation=SimpleNamespace(enabled=True)),
        )
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        data = {
            **SAMPLE_CAMPAIGN_DATA,
            "brief": {**SAMPLE_CAMPAIGN_DATA["brief"], "generate_images": False},
        }
        prompt = agent.build_revision_prompt(task, data)
        assert "IMAGE BRIEF INSTRUCTIONS" not in prompt

    def test_build_revision_prompt_includes_existing_image_brief_data(self, mock_llm):
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        data = {
            **SAMPLE_CAMPAIGN_DATA,
            "content": {
                "theme": "Old Theme",
                "tone_of_voice": "Formal",
                "pieces": [
                    {
                        "content_type": "social_post",
                        "channel": "social_media",
                        "content": "Old social copy",
                        "variant": "A",
                        "image_brief": {
                            "prompt": "A modern team using cloud tools in a bright office",
                            "creative_brief": "Show teamwork and productivity",
                            "suggested_dimensions": "1024x1024",
                        },
                    },
                ],
            },
        }
        prompt = agent.build_revision_prompt(task, data)
        assert "Image brief:" in prompt
        assert "A modern team using cloud tools in a bright office" in prompt

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

    def test_build_piece_revision_prompt_includes_image_brief_when_present(self, mock_llm, monkeypatch):
        monkeypatch.setattr(
            "backend.orchestration.content_creator_agent.get_settings",
            lambda: SimpleNamespace(image_generation=SimpleNamespace(enabled=True)),
        )
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        data = {
            **SAMPLE_CAMPAIGN_DATA,
            "brief": {**SAMPLE_CAMPAIGN_DATA["brief"], "generate_images": True},
        }
        rejected_pieces = [
            {
                "content_type": "social_post",
                "channel": "social_media",
                "content": "Old social copy",
                "variant": "A",
                "human_notes": "Improve visual concept",
                "image_brief": {
                    "prompt": "Office teamwork around dashboard screens, optimistic mood",
                    "creative_brief": "Show productivity in action",
                    "suggested_dimensions": "1024x1024",
                },
            },
        ]
        prompt = agent.build_piece_revision_prompt(task, data, rejected_pieces)
        assert "Current image brief:" in prompt
        assert "Office teamwork around dashboard screens, optimistic mood" in prompt
        assert "IMAGE BRIEF INSTRUCTIONS" in prompt

    async def test_revise_returns_agent_result_on_success(self, mock_llm):
        revised_data = {
            "theme": "Updated Theme",
            "tone_of_voice": "Casual",
            "pieces": [
                {"content_type": "body_copy", "channel": "email", "content": "New copy", "variant": "A", "notes": ""},
            ],
        }
        mock_llm.chat_json = AsyncMock(return_value=json.dumps(revised_data))
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        data = {
            **SAMPLE_CAMPAIGN_DATA,
            "review": {
                "approved": False,
                "issues": ["Tone is too formal"],
                "suggestions": ["Make it casual"],
                "brand_consistency_score": 5.0,
                "review_summary": "Needs work",
            },
        }
        result = await agent.revise(task, data)
        assert result.success is True
        assert result.agent_type == AgentType.CONTENT_CREATOR
        assert result.campaign_id == "c1"
        assert "pieces" in result.output
        assert result.output["pieces"][0]["content"] == "New copy"

    async def test_revise_returns_failed_agent_result_on_llm_error(self, mock_llm):
        mock_llm.chat_json = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        result = await agent.revise(task, SAMPLE_CAMPAIGN_DATA)
        assert result.success is False
        assert "LLM unavailable" in (result.error or "")

    async def test_revise_calls_revision_prompts(self, mock_llm):
        revised_data = {"theme": "T", "tone_of_voice": "Bold", "pieces": []}
        mock_llm.chat_json = AsyncMock(return_value=json.dumps(revised_data))
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        await agent.revise(task, SAMPLE_CAMPAIGN_DATA)
        # Verify the system message uses the revision system prompt
        call_args = mock_llm.chat_json.call_args[0][0]
        assert call_args[0]["role"] == "system"
        assert "improve" in call_args[0]["content"].lower() or "revise" in call_args[0]["content"].lower()

    async def test_revise_pieces_returns_agent_result_on_success(self, mock_llm):
        revised_data = {
            "theme": "T",
            "tone_of_voice": "Bold",
            "pieces": [
                {"content_type": "headline", "channel": "email", "content": "Punchier Headline", "variant": "A", "notes": "Fixed"},
            ],
        }
        mock_llm.chat_json = AsyncMock(return_value=json.dumps(revised_data))
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        rejected = [
            {"content_type": "headline", "channel": "email", "content": "Old Headline", "variant": "A", "human_notes": "Too bland"},
        ]
        result = await agent.revise_pieces(task, SAMPLE_CAMPAIGN_DATA, rejected)
        assert result.success is True
        assert result.output["pieces"][0]["content"] == "Punchier Headline"

    async def test_revise_pieces_returns_failed_agent_result_on_llm_error(self, mock_llm):
        mock_llm.chat_json = AsyncMock(side_effect=ValueError("bad response"))
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        rejected = [
            {"content_type": "body_copy", "channel": "email", "content": "Some text", "variant": "A", "human_notes": "Boring"},
        ]
        result = await agent.revise_pieces(task, SAMPLE_CAMPAIGN_DATA, rejected)
        assert result.success is False
        assert "bad response" in (result.error or "")

    async def test_revise_pieces_calls_piece_revision_prompt(self, mock_llm):
        revised_data = {"theme": "T", "tone_of_voice": "Bold", "pieces": []}
        mock_llm.chat_json = AsyncMock(return_value=json.dumps(revised_data))
        agent = ContentCreatorAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CONTENT_CREATOR)
        rejected = [
            {"content_type": "headline", "channel": "email", "content": "Sync Without Limits", "variant": "A", "human_notes": "Make punchier"},
        ]
        await agent.revise_pieces(task, SAMPLE_CAMPAIGN_DATA, rejected)
        # Verify the user message contains the rejected piece content
        call_args = mock_llm.chat_json.call_args[0][0]
        user_msg = call_args[1]["content"]
        assert "Sync Without Limits" in user_msg
        assert "Make punchier" in user_msg


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

    def test_prompt_includes_platform_breakdown_instruction(self, mock_llm):
        agent = ChannelPlannerAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CHANNEL_PLANNER)
        prompt = agent.build_user_prompt(task, SAMPLE_CAMPAIGN_DATA_WITH_SOCIAL_PLATFORMS)
        assert "Social Media Platforms" in prompt
        assert "platform_breakdown" in prompt
        assert "instagram" in prompt

    def test_parse_response_preserves_platform_breakdown(self, mock_llm):
        agent = ChannelPlannerAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CHANNEL_PLANNER)
        raw = json.dumps({
            "total_budget": 50000,
            "currency": "USD",
            "recommendations": [
                {
                    "channel": "social_media",
                    "budget_pct": 100,
                    "rationale": "High engagement",
                    "platform_breakdown": [
                        {"platform": "Instagram", "budget_pct": 50.0, "tactics": ["Reels ads"]},
                        {"platform": "facebook", "budget_pct": 30.0, "tactics": ["Video ads"]},
                        {"platform": "linkedin", "budget_pct": 20.0, "tactics": ["Sponsored content"]},
                    ],
                }
            ],
        })
        result = agent.parse_response(raw, task)
        breakdown = result["recommendations"][0]["platform_breakdown"]
        assert len(breakdown) == 3
        # Platform names should be lowercased
        assert breakdown[0]["platform"] == "instagram"
        assert breakdown[1]["platform"] == "facebook"
        assert breakdown[2]["platform"] == "linkedin"
        assert breakdown[0]["budget_pct"] == 50.0
        assert breakdown[0]["tactics"] == ["Reels ads"]

    def test_parse_response_removes_empty_platform_breakdown(self, mock_llm):
        agent = ChannelPlannerAgent(llm_service=mock_llm)
        task = _make_task(AgentType.CHANNEL_PLANNER)
        raw = json.dumps({
            "total_budget": 50000,
            "currency": "USD",
            "recommendations": [
                {"channel": "email", "budget_pct": 40, "platform_breakdown": []},
                {"channel": "social_media", "budget_pct": 60, "platform_breakdown": None},
            ],
        })
        result = agent.parse_response(raw, task)
        # Empty list should be removed
        assert "platform_breakdown" not in result["recommendations"][0]
        # None should be removed
        assert "platform_breakdown" not in result["recommendations"][1]

    def test_system_prompt_includes_platform_breakdown_schema(self, mock_llm):
        agent = ChannelPlannerAgent(llm_service=mock_llm)
        prompt = agent.system_prompt()
        assert "platform_breakdown" in prompt


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
