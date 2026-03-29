"""Template recommendation service using accessible template metadata + LLM ranking."""

import json
import logging
from typing import Optional

from backend.apps.api.schemas.campaigns import TemplateRecommendation
from backend.infrastructure.campaign_store import CampaignStore
from backend.infrastructure.llm_service import LLMService

logger = logging.getLogger(__name__)


def _normalize_channels(channels: Optional[str]) -> list[str]:
    if not channels:
        return []
    return [item.strip() for item in channels.split(",") if item.strip()]


async def recommend_templates(
    goal: str,
    product: str,
    channels: Optional[str],
    budget: Optional[float],
    user_id: str,
    workspace_ids: list[str],
    campaign_store: CampaignStore,
    llm_service: LLMService,
) -> list[TemplateRecommendation]:
    """Return up to top-3 ranked template recommendations for the caller context."""
    limit = 200
    offset = 0
    all_templates: list[dict] = []
    while True:
        items, total = await campaign_store.list_templates(
            user_id=user_id,
            workspace_ids=workspace_ids,
            filters={
                "category": None,
                "tags": [],
                "featured": None,
                "visibility": None,
                "search": None,
                "limit": limit,
                "offset": offset,
                "is_admin": False,
            },
        )
        all_templates.extend(items)
        offset += limit
        if offset >= total:
            break

    if not all_templates:
        return []

    channels_list = _normalize_channels(channels)
    template_lines = []
    for item in all_templates:
        template_lines.append(
            (
                f'- id="{item["id"]}" | name="{item.get("name") or ""}" | '
                f'category="{item.get("category") or ""}" | tags={item.get("tags") or []} | '
                f'clone_count={item.get("clone_count", 0)} | '
                f'avg_brand_score={item.get("avg_brand_score")}'
            )
        )

    prompt = (
        "Recommend the top 3 campaign templates for this user context.\n"
        f"Goal: {goal}\n"
        f"Product: {product}\n"
        f"Channels: {channels_list}\n"
        f"Budget: {budget}\n\n"
        "Accessible templates:\n"
        f"{chr(10).join(template_lines)}\n\n"
        "Return strict JSON with this shape:\n"
        '{\n'
        '  "recommendations": [\n'
        '    {"template_id": "string", "rank": 1, "match_reason": "string"}\n'
        "  ]\n"
        "}\n"
        "Rules: choose only IDs from the list, max 3 recommendations, rank starts at 1 and increases."
    )

    try:
        raw = await llm_service.chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a marketing template recommendation assistant. "
                        "Return only valid JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
        )
    except Exception:
        logger.warning("Template recommendations unavailable (LLM call failed).", exc_info=True)
        return []

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Template recommendations: unparseable LLM JSON response: %r", raw[:300])
        return []

    recommendations_raw = payload.get("recommendations")
    if not isinstance(recommendations_raw, list):
        logger.error("Template recommendations: missing/invalid 'recommendations' list")
        return []

    template_lookup = {item["id"]: item for item in all_templates}
    seen_ids: set[str] = set()
    recommendations: list[TemplateRecommendation] = []

    for candidate in recommendations_raw:
        if not isinstance(candidate, dict):
            continue
        template_id = candidate.get("template_id")
        if not isinstance(template_id, str):
            continue
        if template_id not in template_lookup or template_id in seen_ids:
            continue

        rank_raw = candidate.get("rank", len(recommendations) + 1)
        try:
            rank = int(rank_raw)
        except (TypeError, ValueError):
            rank = len(recommendations) + 1
        if rank < 1:
            rank = len(recommendations) + 1

        match_reason = candidate.get("match_reason")
        if not isinstance(match_reason, str) or not match_reason.strip():
            match_reason = "Relevant match based on campaign goal and product context."

        source = template_lookup[template_id]
        recommendations.append(
            TemplateRecommendation(
                template_id=template_id,
                template_name=source.get("name") or "",
                rank=rank,
                match_reason=match_reason.strip(),
            )
        )
        seen_ids.add(template_id)
        if len(recommendations) == 3:
            break

    recommendations.sort(key=lambda item: item.rank)
    return recommendations
