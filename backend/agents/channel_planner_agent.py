"""
Channel Planner Agent — recommends marketing channels, budget allocation,
timing / cadence, and tactical approaches.
"""

from __future__ import annotations

import json
from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.models.messages import AgentTask, AgentType


class ChannelPlannerAgent(BaseAgent):
    agent_type = AgentType.CHANNEL_PLANNER

    def system_prompt(self) -> str:
        return """You are an expert Media Planner and Channel Strategist.
Given a campaign strategy you must recommend the optimal marketing channel mix,
budget allocation, and timing.

You MUST respond with a valid JSON object using exactly this schema:

{
  "total_budget": 50000.00,
  "currency": "USD",
  "recommendations": [
    {
      "channel": "email | social_media | paid_ads | content_marketing | seo | influencer | events | pr",
      "rationale": "Why this channel is recommended",
      "budget_pct": 25.0,
      "timing": "Launch week 1-2, then bi-weekly",
      "tactics": ["tactic 1", "tactic 2"]
    }
  ],
  "timeline_summary": "Overall campaign timeline description"
}

Guidelines:
- Channel values must be one of: email, social_media, paid_ads, content_marketing, seo, influencer, events, pr.
- budget_pct values across all recommendations should sum to 100.
- Justify each channel choice with data-driven rationale.
- Consider the target audience's media consumption habits.
- Include specific tactics (e.g. "LinkedIn sponsored InMail" not just "social_media").
- Provide a realistic timeline with phases (launch, sustain, optimise).
- If budget is not specified, recommend a range and allocate percentages."""

    def build_user_prompt(self, task: AgentTask, campaign_data: dict[str, Any]) -> str:
        brief = campaign_data.get("brief", {})
        strategy = campaign_data.get("strategy", {})

        parts = [
            "Develop a channel plan for this campaign:\n",
            f"**Product/Service:** {brief.get('product_or_service', 'N/A')}",
            f"**Goal:** {brief.get('goal', 'N/A')}",
        ]

        if brief.get("budget"):
            parts.append(
                f"**Budget:** {brief.get('currency', 'USD')} {brief['budget']:,.2f}"
            )
        if brief.get("timeline"):
            parts.append(f"**Timeline:** {brief['timeline']}")

        if strategy:
            parts.append(f"\n**Objectives:**")
            for obj in strategy.get("objectives", []):
                parts.append(f"  - {obj}")
            audience = strategy.get("target_audience", {})
            if audience:
                parts.append(f"**Demographics:** {audience.get('demographics', 'N/A')}")
                parts.append(f"**Psychographics:** {audience.get('psychographics', 'N/A')}")

        selected = brief.get("selected_channels", [])
        if selected:
            labels = [ch.replace("_", " ").title() for ch in selected]
            parts.append(f"\n**Selected Channels:** {', '.join(labels)}")
            parts.append("IMPORTANT: Only include recommendations for the channels listed above. Do not recommend other channels. Allocate 100% of the budget across these channels only.")

        platforms = brief.get("social_media_platforms", [])
        if platforms:
            platform_labels = [p.replace("_", " ").title() for p in platforms]
            parts.append(f"\n**Social Media Platforms:** {', '.join(platform_labels)}")
            parts.append("IMPORTANT: When planning the social_media channel, focus ONLY on the platforms listed above. Tailor tactics, timing, and budget sub-allocation to these specific platforms.")

        if task.instruction:
            parts.append(f"\n**Additional Instructions:** {task.instruction}")

        return "\n".join(parts)

    def parse_response(self, raw: str, task: AgentTask) -> dict[str, Any]:
        data = self._safe_json_parse(raw)
        if "recommendations" not in data:
            data["recommendations"] = []
        return data
