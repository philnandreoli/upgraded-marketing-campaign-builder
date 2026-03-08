"""
Analytics Agent — defines KPIs, tracking tools, reporting cadence,
attribution model, and success criteria for the campaign.
"""

from __future__ import annotations

import json
from typing import Any

from backend.orchestration.base_agent import BaseAgent
from backend.models.messages import AgentTask, AgentType


class AnalyticsAgent(BaseAgent):
    agent_type = AgentType.ANALYTICS

    def system_prompt(self) -> str:
        return """You are a Marketing Analytics and Measurement Expert.
Given a campaign strategy, content plan, and channel plan, you must define
a comprehensive analytics and measurement framework.

You MUST respond with a valid JSON object using exactly this schema:

{
  "kpis": [
    {
      "name": "KPI name",
      "target_value": "Specific numeric target",
      "measurement_method": "How this KPI will be tracked"
    }
  ],
  "tracking_tools": ["Google Analytics 4", "HubSpot", ...],
  "reporting_cadence": "weekly | bi-weekly | monthly",
  "attribution_model": "Description of attribution approach",
  "success_criteria": "What defines campaign success"
}

Guidelines:
- KPIs must be quantifiable with specific targets.
- Include both leading indicators (clicks, impressions) and lagging indicators (conversions, revenue).
- Match KPIs to the SMART objectives from the strategy.
- Recommend specific tracking tools and integrations.
- Define a clear attribution model (first-touch, last-touch, multi-touch, etc.).
- Provide benchmarks where possible.
- Include cost-efficiency metrics (CPA, ROAS, CPL)."""

    def build_user_prompt(self, task: AgentTask, campaign_data: dict[str, Any]) -> str:
        brief = campaign_data.get("brief", {})
        strategy = campaign_data.get("strategy", {})
        channel_plan = campaign_data.get("channel_plan", {})

        parts = [
            "Define the analytics framework for this campaign:\n",
            f"**Product/Service:** {brief.get('product_or_service', 'N/A')}",
            f"**Goal:** {brief.get('goal', 'N/A')}",
        ]

        if brief.get("budget"):
            parts.append(
                f"**Budget:** {brief.get('currency', 'USD')} {brief['budget']:,.2f}"
            )

        if strategy:
            parts.append("\n**Strategic Objectives:**")
            for obj in strategy.get("objectives", []):
                parts.append(f"  - {obj}")
            parts.append(f"**Value Proposition:** {strategy.get('value_proposition', 'N/A')}")

        if channel_plan:
            parts.append("\n**Channel Mix:**")
            for rec in channel_plan.get("recommendations", []):
                parts.append(
                    f"  - {rec.get('channel', 'N/A')} ({rec.get('budget_pct', 0):.0f}% budget)"
                )

        selected = brief.get("selected_channels", [])
        if selected:
            labels = [ch.replace("_", " ").title() for ch in selected]
            parts.append(f"\n**Selected Channels:** {', '.join(labels)}")
            parts.append("Focus KPIs and tracking on these channels only.")

        if task.instruction:
            parts.append(f"\n**Additional Instructions:** {task.instruction}")

        return "\n".join(parts)

    def parse_response(self, raw: str, task: AgentTask) -> dict[str, Any]:
        data = self._safe_json_parse(raw)
        if "kpis" not in data:
            data["kpis"] = []
        return data
