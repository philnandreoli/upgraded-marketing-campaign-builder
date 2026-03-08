"""
Review / QA Agent — reviews the full campaign for quality, brand consistency,
and completeness, then flags issues for human approval.

This agent supports human-in-the-loop: after the AI review it sets
`requires_human_approval = True` so the Coordinator pauses for a human decision.

It can also generate follow-up clarification questions from its own review
output so the user can provide guidance for improving low-scoring areas.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.orchestration.base_agent import BaseAgent
from backend.models.messages import AgentMessage, AgentResult, AgentTask, AgentType, MessageRole

logger = logging.getLogger(__name__)


class ReviewQAAgent(BaseAgent):
    agent_type = AgentType.REVIEW_QA

    # Flag inspected by the Coordinator to decide whether to pause
    requires_human_approval: bool = True

    def system_prompt(self) -> str:
        return """You are a Senior Marketing Quality Assurance Reviewer and Brand Guardian.
Your job is to review a complete marketing campaign (strategy, content, channel plan,
and analytics) and assess it for quality, consistency, and completeness.

You MUST respond with a valid JSON object using exactly this schema:

{
  "approved": false,
  "issues": [
    "Issue description 1",
    "Issue description 2"
  ],
  "suggestions": [
    "Improvement suggestion 1",
    "Improvement suggestion 2"
  ],
  "brand_consistency_score": 7.5,
  "section_scores": {
    "strategy": 8.0,
    "content": 7.0,
    "channel_plan": 7.5,
    "analytics": 8.5
  },
  "review_summary": "Overall assessment paragraph"
}

Review criteria:
1. **Strategic Alignment** — Do all elements support the stated objectives?
2. **Target Audience Fit** — Is the messaging appropriate for the defined audience?
3. **Content Quality** — Are headlines compelling? CTAs clear? Copy error-free?
4. **Channel Coherence** — Does the channel mix make sense for the audience and budget?
5. **Measurement Readiness** — Are KPIs tied to objectives? Are tracking tools realistic?
6. **Brand Consistency** — Is tone/voice consistent across all content pieces?
7. **Budget Feasibility** — Do allocations seem realistic?
8. **Completeness** — Are there any gaps or missing elements?

Scoring: 0-10 scale (10 = perfect).
Set "approved" to true ONLY if there are zero critical issues and brand_consistency_score >= 7.0.
Always provide actionable suggestions even if approving."""

    def build_user_prompt(self, task: AgentTask, campaign_data: dict[str, Any]) -> str:
        brief = campaign_data.get("brief", {})
        strategy = campaign_data.get("strategy", {})
        content = campaign_data.get("content", {})
        channel_plan = campaign_data.get("channel_plan", {})
        analytics_plan = campaign_data.get("analytics_plan", {})

        parts = ["Please review the following complete marketing campaign:\n"]

        # Brief
        parts.append("## Campaign Brief")
        parts.append(f"**Product/Service:** {brief.get('product_or_service', 'N/A')}")
        parts.append(f"**Goal:** {brief.get('goal', 'N/A')}")
        if brief.get("budget"):
            parts.append(f"**Budget:** {brief.get('currency', 'USD')} {brief['budget']:,.2f}")
        if brief.get("start_date") and brief.get("end_date"):
            parts.append(f"**Timeline:** {brief['start_date']} to {brief['end_date']}")

        # Strategy
        if strategy:
            parts.append("\n## Strategy")
            parts.append(f"**Value Proposition:** {strategy.get('value_proposition', 'N/A')}")
            parts.append(f"**Positioning:** {strategy.get('positioning', 'N/A')}")
            parts.append("**Objectives:**")
            for obj in strategy.get("objectives", []):
                parts.append(f"  - {obj}")
            parts.append("**Key Messages:**")
            for msg in strategy.get("key_messages", []):
                parts.append(f"  - {msg}")

        # Content
        if content:
            parts.append("\n## Content")
            parts.append(f"**Theme:** {content.get('theme', 'N/A')}")
            parts.append(f"**Tone:** {content.get('tone_of_voice', 'N/A')}")
            parts.append(f"**Number of pieces:** {len(content.get('pieces', []))}")
            for i, piece in enumerate(content.get("pieces", [])[:5], 1):
                parts.append(
                    f"  {i}. [{piece.get('content_type')}] ({piece.get('channel', 'general')}) "
                    f"— {piece.get('content', '')[:120]}..."
                )
            if len(content.get("pieces", [])) > 5:
                parts.append(f"  ... and {len(content['pieces']) - 5} more pieces")

        # Channel Plan
        if channel_plan:
            parts.append("\n## Channel Plan")
            parts.append(f"**Total Budget:** {channel_plan.get('currency', 'USD')} {channel_plan.get('total_budget', 0):,.2f}")
            for rec in channel_plan.get("recommendations", []):
                parts.append(
                    f"  - **{rec.get('channel', 'N/A')}** — {rec.get('budget_pct', 0):.0f}% — {rec.get('rationale', '')[:100]}"
                )

        # Analytics
        if analytics_plan:
            parts.append("\n## Analytics Plan")
            parts.append(f"**Reporting:** {analytics_plan.get('reporting_cadence', 'N/A')}")
            parts.append(f"**Attribution:** {analytics_plan.get('attribution_model', 'N/A')}")
            parts.append("**KPIs:**")
            for kpi in analytics_plan.get("kpis", []):
                parts.append(f"  - {kpi.get('name', 'N/A')}: target {kpi.get('target_value', 'N/A')}")

        selected = brief.get("selected_channels", [])
        if selected:
            labels = [ch.replace("_", " ").title() for ch in selected]
            parts.append(f"\n**Selected Channels:** {', '.join(labels)}")
            parts.append("Verify that all content and channel recommendations are limited to the selected channels only. Flag any content produced for non-selected channels as an issue.")

        if task.instruction:
            parts.append(f"\n**Additional Review Instructions:** {task.instruction}")

        return "\n".join(parts)

    def parse_response(self, raw: str, task: AgentTask) -> dict[str, Any]:
        data = self._safe_json_parse(raw)
        # Normalise the approved flag
        data.setdefault("approved", False)
        data.setdefault("issues", [])
        data.setdefault("suggestions", [])
        data.setdefault("brand_consistency_score", 0.0)
        # The Coordinator will read `requires_human_approval` to pause the pipeline
        data["requires_human_approval"] = self.requires_human_approval
        return data
