"""AI-assisted experiment insights endpoint."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from backend.apps.api.dependencies import get_campaign_for_read
from backend.apps.api.schemas.experiments import ExperimentInsightsResponse
from backend.infrastructure.experiment_store import get_experiment_store
from backend.infrastructure.llm_service import get_llm_service
from backend.models.campaign import Campaign

router = APIRouter(tags=["experiments"])


@router.get(
    "/campaigns/{campaign_id}/experiments/{exp_id}/insights",
    response_model=ExperimentInsightsResponse,
)
async def get_experiment_insights(
    campaign_id: str,
    exp_id: str,
    campaign: Campaign = Depends(get_campaign_for_read),
) -> ExperimentInsightsResponse:
    experiment = await get_experiment_store().get_experiment(exp_id)
    if experiment is None or experiment.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Experiment not found")

    metrics = await get_experiment_store().list_variant_metrics(exp_id)
    by_variant: dict[str, dict[str, float]] = {}
    for metric in metrics:
        bucket = by_variant.setdefault(
            metric.variant,
            {"impressions": 0.0, "clicks": 0.0, "conversions": 0.0, "revenue": 0.0},
        )
        bucket["impressions"] += metric.impressions
        bucket["clicks"] += metric.clicks
        bucket["conversions"] += metric.conversions
        bucket["revenue"] += metric.revenue

    fallback = {
        "summary": "Variant performance analysis generated from recorded metrics.",
        "experiment_status": experiment.status.value,
        "winner_variant": experiment.winner_variant,
        "variant_breakdown": by_variant,
        "recommendations": [
            "Increase sample size for low-impression variants before selecting winner."
            if any(item["impressions"] < experiment.config.min_sample_size for item in by_variant.values())
            else "Traffic volume is sufficient to evaluate winner confidence."
        ],
    }

    try:
        llm_messages = [
            {
                "role": "system",
                "content": (
                    "You are a marketing experimentation analyst. "
                    "Return strict JSON with keys: summary, winner_hypothesis, risks, recommendations."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Generate experiment insights from this payload:\n"
                    f"{json.dumps({'experiment': experiment.model_dump(mode='json'), 'variants': by_variant})}"
                ),
            },
        ]
        raw = await get_llm_service().chat_json(llm_messages, max_tokens=900)
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            fallback.update(parsed)
    except Exception:
        pass

    return ExperimentInsightsResponse(
        experiment_id=experiment.id,
        campaign_id=campaign.id,
        insights=fallback,
    )
