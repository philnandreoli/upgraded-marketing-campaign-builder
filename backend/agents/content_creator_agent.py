"""
Content Creator Agent — generates copy, headlines, CTAs, social posts,
and email content aligned with the campaign strategy.
"""

from __future__ import annotations

import json
from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.models.messages import AgentTask, AgentType


class ContentCreatorAgent(BaseAgent):
    agent_type = AgentType.CONTENT_CREATOR

    def system_prompt(self) -> str:
        return """You are a world-class Marketing Copywriter and Content Creator.
Given a campaign strategy you must produce compelling marketing content across
multiple channels and formats.

You MUST respond with a valid JSON object using exactly this schema:

{
  "theme": "Overall creative theme / big idea",
  "tone_of_voice": "Description of tone (e.g. bold & playful, professional & trustworthy)",
  "pieces": [
    {
      "content_type": "headline | body_copy | cta | social_post | email_subject | email_body | ad_copy | tagline",
      "channel": "email | social_media | paid_ads | content_marketing | website",
      "content": "The actual copy text",
      "variant": "A",
      "notes": "Rationale or usage guidance"
    }
  ]
}

Guidelines:
- Provide A/B variants for headlines and CTAs.
- Tailor tone and length to each channel.
- Headlines: punchy, benefit-driven, under 10 words.
- CTAs: action-oriented, create urgency.
- Email subjects: curiosity-driven, under 50 characters.
- Social posts: appropriate length per platform, include hashtag suggestions.
- Ensure all content reinforces the key messages from the strategy.
- Produce at least 8-10 content pieces across multiple channels."""

    def build_user_prompt(self, task: AgentTask, campaign_data: dict[str, Any]) -> str:
        brief = campaign_data.get("brief", {})
        strategy = campaign_data.get("strategy", {})

        parts = [
            "Create marketing content for this campaign:\n",
            f"**Product/Service:** {brief.get('product_or_service', 'N/A')}",
            f"**Goal:** {brief.get('goal', 'N/A')}",
        ]

        if strategy:
            parts.append(f"\n**Value Proposition:** {strategy.get('value_proposition', 'N/A')}")
            parts.append(f"**Positioning:** {strategy.get('positioning', 'N/A')}")
            key_msgs = strategy.get("key_messages", [])
            if key_msgs:
                parts.append("**Key Messages:**")
                for msg in key_msgs:
                    parts.append(f"  - {msg}")
            audience = strategy.get("target_audience", {})
            if audience:
                parts.append(f"**Target Demographics:** {audience.get('demographics', 'N/A')}")
                parts.append(f"**Target Psychographics:** {audience.get('psychographics', 'N/A')}")

        selected = brief.get("selected_channels", [])
        if selected:
            labels = [ch.replace("_", " ").title() for ch in selected]
            parts.append(f"\n**Selected Channels:** {', '.join(labels)}")
            parts.append("IMPORTANT: Only create content for the channels listed above. Do not produce content for other channels.")

        platforms = brief.get("social_media_platforms", [])
        if platforms:
            platform_labels = [p.replace("_", " ").title() for p in platforms]
            parts.append(f"\n**Social Media Platforms:** {', '.join(platform_labels)}")
            parts.append("IMPORTANT: When creating social media content, create platform-specific posts ONLY for the platforms listed above. Tailor format, tone, and length to each platform's best practices.")

        if task.instruction:
            parts.append(f"\n**Additional Instructions:** {task.instruction}")

        return "\n".join(parts)

    def parse_response(self, raw: str, task: AgentTask) -> dict[str, Any]:
        data = self._safe_json_parse(raw)
        pieces = data.get("pieces", [])
        if not isinstance(pieces, list):
            pieces = []

        cleaned_pieces = []
        for piece in pieces:
            if not isinstance(piece, dict):
                continue

            content = str(piece.get("content", "")).strip()
            content_type = str(piece.get("content_type", "")).strip()

            if not content or not content_type:
                continue

            cleaned_pieces.append({
                "content_type": content_type,
                "channel": str(piece.get("channel", "")).strip(),
                "content": content,
                "variant": str(piece.get("variant", "A") or "A").strip() or "A",
                "notes": str(piece.get("notes", "")).strip(),
            })

        data["pieces"] = cleaned_pieces
        return data

    # ------------------------------------------------------------------
    # Revision support: Improve content based on review feedback
    # ------------------------------------------------------------------

    def revision_system_prompt(self) -> str:
        """System prompt for the review-driven content revision pass."""
        return """You are a world-class Marketing Copywriter and Content Creator.
You previously created campaign content that has been reviewed by a QA team.
You are now given the review feedback (issues and suggestions) along with the
original brief, strategy, and your previous content.

Your job is to IMPROVE every content piece, addressing every issue and
incorporating the suggestions while keeping the original intent and strategy intact.

You MUST respond with a valid JSON object using exactly this schema:

{
  "theme": "Overall creative theme / big idea (may be updated)",
  "tone_of_voice": "Description of tone (may be updated)",
  "pieces": [
    {
      "content_type": "headline | body_copy | cta | social_post | email_subject | email_body | ad_copy | tagline",
      "channel": "email | social_media | paid_ads | content_marketing | website",
      "content": "The IMPROVED copy text",
      "variant": "A",
      "notes": "What was changed and why"
    }
  ]
}

Guidelines:
- Address EVERY issue raised in the review.
- Incorporate ALL suggestions where possible.
- Maintain or improve A/B variants for headlines and CTAs.
- Keep the same number of content pieces (or more) — do not drop any.
- In the notes field for each piece, briefly describe what you improved.
- Ensure all content reinforces the key messages from the strategy.
- Maintain channel-appropriate tone, length, and formatting."""

    def build_revision_prompt(
        self, task: AgentTask, campaign_data: dict[str, Any]
    ) -> str:
        """Build user prompt that includes original content + review feedback."""
        brief = campaign_data.get("brief", {})
        strategy = campaign_data.get("strategy", {})
        content = campaign_data.get("content", {})
        review = campaign_data.get("review", {})
        clarification_answers = campaign_data.get("clarification_answers", {})
        clarification_questions = campaign_data.get("clarification_questions", [])

        parts = [
            "Improve the following marketing content based on the review feedback:\n",
            "## Campaign Brief",
            f"**Product/Service:** {brief.get('product_or_service', 'N/A')}",
            f"**Goal:** {brief.get('goal', 'N/A')}",
        ]

        if brief.get("budget"):
            parts.append(f"**Budget:** {brief.get('currency', 'USD')} {brief['budget']:,.2f}")
        if brief.get("start_date") and brief.get("end_date"):
            parts.append(f"**Timeline:** {brief['start_date']} to {brief['end_date']}")
        if brief.get("additional_context"):
            parts.append(f"**Additional Context:** {brief['additional_context']}")

        # Clarification Q&A
        if clarification_questions and clarification_answers:
            parts.append("\n## Clarification Q&A")
            for q in clarification_questions:
                qid = q.get("id", "")
                answer = clarification_answers.get(qid, "")
                if answer:
                    parts.append(f"  Q: {q.get('question', '')}")
                    parts.append(f"  A: {answer}")

        # Strategy
        if strategy:
            parts.append("\n## Strategy")
            parts.append(f"**Value Proposition:** {strategy.get('value_proposition', 'N/A')}")
            parts.append(f"**Positioning:** {strategy.get('positioning', 'N/A')}")
            key_msgs = strategy.get("key_messages", [])
            if key_msgs:
                parts.append("**Key Messages:**")
                for msg in key_msgs:
                    parts.append(f"  - {msg}")
            audience = strategy.get("target_audience", {})
            if audience:
                parts.append(f"**Target Demographics:** {audience.get('demographics', 'N/A')}")
                parts.append(f"**Target Psychographics:** {audience.get('psychographics', 'N/A')}")

        # Original content
        if content:
            parts.append("\n## Original Content (to improve)")
            parts.append(f"**Theme:** {content.get('theme', 'N/A')}")
            parts.append(f"**Tone:** {content.get('tone_of_voice', 'N/A')}")
            for i, piece in enumerate(content.get("pieces", []), 1):
                parts.append(
                    f"\n### Piece {i}: [{piece.get('content_type')}] ({piece.get('channel', 'general')}) "
                    f"Variant {piece.get('variant', 'A')}"
                )
                parts.append(f"```\n{piece.get('content', '')}\n```")
                if piece.get("notes"):
                    parts.append(f"Notes: {piece['notes']}")

        # Review feedback
        if review:
            parts.append("\n## Review Feedback — MUST ADDRESS ALL ITEMS")
            parts.append(f"**Brand Consistency Score:** {review.get('brand_consistency_score', 0)}/10")

            issues = review.get("issues", [])
            if issues:
                parts.append("\n**Issues (MUST FIX):**")
                for i, issue in enumerate(issues, 1):
                    parts.append(f"  {i}. {issue}")

            suggestions = review.get("suggestions", [])
            if suggestions:
                parts.append("\n**Suggestions (SHOULD INCORPORATE):**")
                for i, s in enumerate(suggestions, 1):
                    parts.append(f"  {i}. {s}")

        selected = brief.get("selected_channels", [])
        if selected:
            labels = [ch.replace("_", " ").title() for ch in selected]
            parts.append(f"\n**Selected Channels:** {', '.join(labels)}")
            parts.append("IMPORTANT: Only create content for the channels listed above.")

        platforms = brief.get("social_media_platforms", [])
        if platforms:
            platform_labels = [p.replace("_", " ").title() for p in platforms]
            parts.append(f"\n**Social Media Platforms:** {', '.join(platform_labels)}")

        if task.instruction:
            parts.append(f"\n**Additional Instructions:** {task.instruction}")

        return "\n".join(parts)

    def build_piece_revision_prompt(
        self, task: AgentTask, campaign_data: dict[str, Any],
        rejected_pieces: list[dict[str, Any]],
    ) -> str:
        """Build user prompt to revise only specific rejected pieces."""
        brief = campaign_data.get("brief", {})
        strategy = campaign_data.get("strategy", {})

        parts = [
            "Revise ONLY the following rejected content pieces based on reviewer notes:\n",
            f"**Product/Service:** {brief.get('product_or_service', 'N/A')}",
            f"**Goal:** {brief.get('goal', 'N/A')}",
        ]

        if strategy:
            parts.append(f"**Value Proposition:** {strategy.get('value_proposition', 'N/A')}")
            key_msgs = strategy.get("key_messages", [])
            if key_msgs:
                parts.append("**Key Messages:** " + "; ".join(key_msgs))

        parts.append("\n## Rejected Pieces to Revise")
        for rp in rejected_pieces:
            parts.append(
                f"\n### [{rp.get('content_type')}] ({rp.get('channel', 'general')}) "
                f"Variant {rp.get('variant', 'A')}"
            )
            parts.append(f"Current content:\n```\n{rp.get('content', '')}\n```")
            if rp.get("human_notes"):
                parts.append(f"**Reviewer notes:** {rp['human_notes']}")

        parts.append(
            "\nProduce improved versions for ONLY the pieces above. "
            "Return the same JSON schema with just these pieces."
        )

        return "\n".join(parts)
