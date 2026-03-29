"""A/B testing experiment and variant metrics API."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from backend.api.workspaces import WorkspaceAction, _authorize_workspace
from backend.apps.api.dependencies import get_campaign_for_read, get_campaign_for_write
from backend.apps.api.schemas.experiments import (
    BulkImportMetricsRequest,
    ConcludeExperimentResponse,
    CreateExperimentRequest,
    ExperimentForecastResponse,
    ExperimentLearningRequest,
    ExperimentLearningResponse,
    ExperimentReportResponse,
    ExperimentResponse,
    ExportExperimentResponse,
    RecordVariantMetricRequest,
    SampleSizeCalculatorResponse,
    SelectWinnerRequest,
    UpdateExperimentRequest,
    VariantComparisonItem,
    VariantMetricResponse,
)
from backend.infrastructure.auth import get_current_user
from backend.infrastructure.campaign_store import get_campaign_store
from backend.infrastructure.experiment_store import get_experiment_store
from backend.models.campaign import Campaign
from backend.models.experiments import Experiment, ExperimentLearning, ExperimentStatus, MetricSource, VariantMetric
from backend.models.user import User
from backend.services.auto_winner_service import evaluate_auto_winner
from backend.services.performance_forecasting import forecast_performance
from backend.services.sample_size_calculator import calculate_sample_size
from backend.services.statistical_significance import bayesian_ab_test, calculate_lift, chi_squared_test

router = APIRouter(tags=["experiments"])
global_router = APIRouter(tags=["experiments"])


def _to_experiment_response(experiment: Experiment) -> ExperimentResponse:
    return ExperimentResponse.model_validate(experiment.model_dump())


def _to_metric_response(metric: VariantMetric) -> VariantMetricResponse:
    return VariantMetricResponse.model_validate(metric.model_dump())


def _to_learning_response(learning: ExperimentLearning) -> ExperimentLearningResponse:
    return ExperimentLearningResponse.model_validate(learning.model_dump())


async def _get_workspace_or_404(workspace_id: str):
    campaign_store = get_campaign_store()
    workspace = await campaign_store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace, campaign_store


async def _get_experiment_for_campaign_or_404(campaign_id: str, exp_id: str) -> Experiment:
    experiment = await get_experiment_store().get_experiment(exp_id)
    if experiment is None or experiment.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return experiment


def _aggregate_metrics(metrics: list[VariantMetric]) -> list[VariantComparisonItem]:
    buckets: dict[str, dict[str, float]] = {}
    for metric in metrics:
        b = buckets.setdefault(
            metric.variant,
            {"impressions": 0.0, "clicks": 0.0, "conversions": 0.0, "revenue": 0.0},
        )
        b["impressions"] += metric.impressions
        b["clicks"] += metric.clicks
        b["conversions"] += metric.conversions
        b["revenue"] += metric.revenue

    rows: list[VariantComparisonItem] = []
    for variant, agg in buckets.items():
        impressions = int(agg["impressions"])
        clicks = int(agg["clicks"])
        conversions = int(agg["conversions"])
        rows.append(
            VariantComparisonItem(
                variant=variant,
                impressions=impressions,
                clicks=clicks,
                conversions=conversions,
                revenue=float(agg["revenue"]),
                ctr=(clicks / impressions) if impressions > 0 else 0.0,
                conversion_rate=(conversions / impressions) if impressions > 0 else 0.0,
            )
        )
    return sorted(rows, key=lambda r: r.variant)


@router.post("/campaigns/{campaign_id}/experiments", response_model=ExperimentResponse, status_code=201)
async def create_experiment(
    campaign_id: str,
    body: CreateExperimentRequest = Body(),
    campaign: Campaign = Depends(get_campaign_for_write),
) -> ExperimentResponse:
    if campaign.workspace_id is None:
        raise HTTPException(status_code=400, detail="Campaign must belong to a workspace")
    experiment = Experiment(
        campaign_id=campaign.id,
        workspace_id=campaign.workspace_id,
        variant_group=body.variant_group,
        name=body.name,
        config=body.config.model_dump(),
    )
    created = await get_experiment_store().create_experiment(experiment)
    return _to_experiment_response(created)


@router.get("/campaigns/{campaign_id}/experiments", response_model=list[ExperimentResponse])
async def list_experiments(
    campaign_id: str,
    campaign: Campaign = Depends(get_campaign_for_read),
) -> list[ExperimentResponse]:
    items = await get_experiment_store().list_experiments_by_campaign(campaign.id)
    return [_to_experiment_response(item) for item in items]


@router.get("/campaigns/{campaign_id}/experiments/{exp_id}", response_model=ExperimentResponse)
async def get_experiment(
    campaign_id: str,
    exp_id: str,
    campaign: Campaign = Depends(get_campaign_for_read),
) -> ExperimentResponse:
    experiment = await _get_experiment_for_campaign_or_404(campaign.id, exp_id)
    return _to_experiment_response(experiment)


@router.patch("/campaigns/{campaign_id}/experiments/{exp_id}", response_model=ExperimentResponse)
async def update_experiment(
    campaign_id: str,
    exp_id: str,
    body: UpdateExperimentRequest = Body(),
    campaign: Campaign = Depends(get_campaign_for_write),
) -> ExperimentResponse:
    existing = await _get_experiment_for_campaign_or_404(campaign.id, exp_id)
    status = body.status.value if body.status is not None else None
    updated = await get_experiment_store().update_experiment(
        existing.id,
        name=body.name,
        status=status,
        config=body.config.model_dump() if body.config is not None else None,
        started_at=datetime.utcnow() if body.status == ExperimentStatus.RUNNING and existing.started_at is None else None,
        concluded_at=datetime.utcnow() if body.status == ExperimentStatus.CONCLUDED else None,
    )
    return _to_experiment_response(updated)


@router.post("/campaigns/{campaign_id}/experiments/{exp_id}/metrics", response_model=VariantMetricResponse, status_code=201)
async def record_variant_metric(
    campaign_id: str,
    exp_id: str,
    body: RecordVariantMetricRequest = Body(),
    campaign: Campaign = Depends(get_campaign_for_write),
) -> VariantMetricResponse:
    experiment = await _get_experiment_for_campaign_or_404(campaign.id, exp_id)
    metric = VariantMetric(
        experiment_id=experiment.id,
        campaign_id=campaign.id,
        content_piece_index=body.content_piece_index,
        variant=body.variant,
        impressions=body.impressions,
        clicks=body.clicks,
        conversions=body.conversions,
        revenue=body.revenue,
        custom_metrics=body.custom_metrics,
        source=body.source,
    )
    created = await get_experiment_store().create_variant_metric(metric)
    return _to_metric_response(created)


@router.get("/campaigns/{campaign_id}/experiments/{exp_id}/metrics", response_model=list[VariantMetricResponse])
async def get_metrics(
    campaign_id: str,
    exp_id: str,
    campaign: Campaign = Depends(get_campaign_for_read),
) -> list[VariantMetricResponse]:
    _ = await _get_experiment_for_campaign_or_404(campaign.id, exp_id)
    metrics = await get_experiment_store().list_variant_metrics(exp_id)
    return [_to_metric_response(m) for m in metrics]


@router.post("/campaigns/{campaign_id}/experiments/{exp_id}/metrics/import", response_model=list[VariantMetricResponse], status_code=201)
async def import_metrics(
    campaign_id: str,
    exp_id: str,
    body: BulkImportMetricsRequest = Body(),
    campaign: Campaign = Depends(get_campaign_for_write),
) -> list[VariantMetricResponse]:
    experiment = await _get_experiment_for_campaign_or_404(campaign.id, exp_id)
    records: list[RecordVariantMetricRequest] = list(body.metrics)
    if body.csv_data:
        reader = csv.DictReader(io.StringIO(body.csv_data))
        for row_num, row in enumerate(reader, start=2):  # row 1 is the header
            try:
                records.append(
                    RecordVariantMetricRequest(
                        content_piece_index=int(row.get("content_piece_index", "0")),
                        variant=str(row.get("variant", "")).strip(),
                        impressions=int(row.get("impressions", "0")),
                        clicks=int(row.get("clicks", "0")),
                        conversions=int(row.get("conversions", "0")),
                        revenue=float(row.get("revenue", "0") or 0),
                        custom_metrics={},
                        source=MetricSource.CSV,
                    )
                )
            except (ValueError, KeyError) as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"CSV parse error on row {row_num}: {exc}",
                ) from exc
    metrics = [
        VariantMetric(
            experiment_id=experiment.id,
            campaign_id=campaign.id,
            content_piece_index=item.content_piece_index,
            variant=item.variant,
            impressions=item.impressions,
            clicks=item.clicks,
            conversions=item.conversions,
            revenue=item.revenue,
            custom_metrics=item.custom_metrics,
            source=item.source,
        )
        for item in records
    ]
    created = await get_experiment_store().bulk_create_variant_metrics(metrics)
    return [_to_metric_response(m) for m in created]


@router.post("/campaigns/{campaign_id}/experiments/{exp_id}/webhook", response_model=VariantMetricResponse, status_code=201)
async def webhook_metric_ingest(
    campaign_id: str,
    exp_id: str,
    payload: dict = Body(default_factory=dict),
    campaign: Campaign = Depends(get_campaign_for_write),
) -> VariantMetricResponse:
    experiment = await _get_experiment_for_campaign_or_404(campaign.id, exp_id)
    metric = VariantMetric(
        experiment_id=experiment.id,
        campaign_id=campaign.id,
        content_piece_index=int(payload.get("content_piece_index", 0)),
        variant=str(payload.get("variant", "A")),
        impressions=int(payload.get("impressions", 0)),
        clicks=int(payload.get("clicks", 0)),
        conversions=int(payload.get("conversions", 0)),
        revenue=float(payload.get("revenue", 0.0) or 0.0),
        custom_metrics=payload.get("custom_metrics", {}) or {},
        source=MetricSource.WEBHOOK,
    )
    created = await get_experiment_store().create_variant_metric(metric)
    return _to_metric_response(created)


@router.get("/campaigns/{campaign_id}/experiments/{exp_id}/report", response_model=ExperimentReportResponse)
async def get_experiment_report(
    campaign_id: str,
    exp_id: str,
    campaign: Campaign = Depends(get_campaign_for_read),
) -> ExperimentReportResponse:
    experiment = await _get_experiment_for_campaign_or_404(campaign.id, exp_id)
    metrics = await get_experiment_store().list_variant_metrics(exp_id)
    variants = _aggregate_metrics(metrics)

    pairwise_statistics: list[dict] = []
    if len(variants) >= 2:
        control = next((v for v in variants if v.variant.upper() == "A"), variants[0])
        for variant in variants:
            if variant.variant == control.variant:
                continue
            freq = chi_squared_test(
                control.conversions,
                control.impressions,
                variant.conversions,
                variant.impressions,
            )
            bayes = bayesian_ab_test(
                control.conversions,
                control.impressions,
                variant.conversions,
                variant.impressions,
            )
            pairwise_statistics.append(
                {
                    "control": control.variant,
                    "variant": variant.variant,
                    "lift": calculate_lift(control.conversion_rate, variant.conversion_rate),
                    "frequentist": freq,
                    "bayesian": bayes,
                }
            )

    return ExperimentReportResponse(
        experiment_id=experiment.id,
        campaign_id=campaign.id,
        status=experiment.status,
        winner_variant=experiment.winner_variant,
        variants=variants,
        pairwise_statistics=pairwise_statistics,
    )


@router.get("/campaigns/{campaign_id}/experiments/{exp_id}/forecast", response_model=ExperimentForecastResponse)
async def get_experiment_forecast(
    campaign_id: str,
    exp_id: str,
    days_ahead: int = Query(default=30, ge=1, le=365),
    campaign: Campaign = Depends(get_campaign_for_read),
) -> ExperimentForecastResponse:
    _ = await _get_experiment_for_campaign_or_404(campaign.id, exp_id)
    metrics = await get_experiment_store().list_variant_metrics(exp_id)
    forecast = forecast_performance(metrics, days_ahead=days_ahead)
    return ExperimentForecastResponse.model_validate(forecast)


@router.patch("/campaigns/{campaign_id}/experiments/{exp_id}/select-winner", response_model=ExperimentResponse)
async def select_winner(
    campaign_id: str,
    exp_id: str,
    body: SelectWinnerRequest = Body(),
    campaign: Campaign = Depends(get_campaign_for_write),
) -> ExperimentResponse:
    experiment = await _get_experiment_for_campaign_or_404(campaign.id, exp_id)
    updated = await get_experiment_store().update_experiment(
        experiment.id,
        winner_variant=body.winner_variant,
    )

    if campaign.content is not None:
        changed = False
        for piece in campaign.content.pieces:
            if piece.variant_group == experiment.variant_group:
                piece.is_winner = piece.variant == body.winner_variant
                changed = True
        if changed:
            campaign.updated_at = datetime.utcnow()
            await get_campaign_store().update(campaign)

    return _to_experiment_response(updated)


@router.post("/campaigns/{campaign_id}/experiments/{exp_id}/conclude", response_model=ConcludeExperimentResponse)
async def conclude_experiment(
    campaign_id: str,
    exp_id: str,
    campaign: Campaign = Depends(get_campaign_for_write),
) -> ConcludeExperimentResponse:
    experiment = await _get_experiment_for_campaign_or_404(campaign.id, exp_id)
    metrics = await get_experiment_store().list_variant_metrics(experiment.id)
    auto_winner = evaluate_auto_winner(experiment, metrics)
    winner = auto_winner or experiment.winner_variant
    updated = await get_experiment_store().update_experiment(
        experiment.id,
        status=ExperimentStatus.CONCLUDED.value,
        concluded_at=datetime.utcnow(),
        winner_variant=winner,
    )
    return ConcludeExperimentResponse(
        experiment=_to_experiment_response(updated),
        auto_selected_winner=auto_winner,
    )


@router.get("/campaigns/{campaign_id}/experiments/{exp_id}/export", response_model=ExportExperimentResponse)
async def export_experiment(
    campaign_id: str,
    exp_id: str,
    fmt: str = Query(default="json", pattern="^(json|csv)$"),
    campaign: Campaign = Depends(get_campaign_for_read),
) -> ExportExperimentResponse:
    experiment = await _get_experiment_for_campaign_or_404(campaign.id, exp_id)
    metrics = await get_experiment_store().list_variant_metrics(exp_id)
    payload = {
        "experiment": experiment.model_dump(),
        "metrics": [m.model_dump(mode="json") for m in metrics],
    }
    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "id",
                "variant",
                "content_piece_index",
                "impressions",
                "clicks",
                "conversions",
                "revenue",
                "source",
                "recorded_at",
            ]
        )
        for metric in metrics:
            writer.writerow(
                [
                    metric.id,
                    metric.variant,
                    metric.content_piece_index,
                    metric.impressions,
                    metric.clicks,
                    metric.conversions,
                    metric.revenue,
                    metric.source.value,
                    metric.recorded_at.isoformat(),
                ]
            )
        data = output.getvalue()
        return ExportExperimentResponse(format="csv", content_type="text/csv", data=data)
    return ExportExperimentResponse(
        format="json",
        content_type="application/json",
        data=json.dumps(payload, default=str),
    )


@router.get("/experiment-learnings", response_model=list[ExperimentLearningResponse])
async def list_experiment_learnings(
    workspace_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> list[ExperimentLearningResponse]:
    _, campaign_store = await _get_workspace_or_404(workspace_id)
    await _authorize_workspace(workspace_id, user, WorkspaceAction.READ, campaign_store)
    items = await get_experiment_store().list_learnings_by_workspace(workspace_id)
    return [_to_learning_response(item) for item in items]


@router.post("/experiment-learnings", response_model=ExperimentLearningResponse, status_code=201)
async def create_experiment_learning(
    workspace_id: str,
    body: ExperimentLearningRequest = Body(),
    user: Optional[User] = Depends(get_current_user),
) -> ExperimentLearningResponse:
    _, campaign_store = await _get_workspace_or_404(workspace_id)
    await _authorize_workspace(workspace_id, user, WorkspaceAction.WRITE, campaign_store)
    experiment = await get_experiment_store().get_experiment(body.experiment_id)
    if experiment is None or experiment.workspace_id != workspace_id or experiment.campaign_id != body.campaign_id:
        raise HTTPException(status_code=404, detail="Experiment not found")
    learning = ExperimentLearning(
        experiment_id=body.experiment_id,
        campaign_id=body.campaign_id,
        workspace_id=workspace_id,
        summary=body.summary,
        tags=body.tags,
        ai_generated=body.ai_generated,
    )
    created = await get_experiment_store().create_learning(learning)
    return _to_learning_response(created)


@global_router.get("/experiments/sample-size-calculator", response_model=SampleSizeCalculatorResponse)
async def sample_size_calculator(
    baseline_rate: float = Query(..., gt=0, lt=1),
    mde: float = Query(..., gt=0),
    confidence_level: float = Query(default=0.95, gt=0.5, lt=1),
    power: float = Query(default=0.8, gt=0.5, lt=1),
    daily_traffic: int = Query(default=0, ge=0),
) -> SampleSizeCalculatorResponse:
    data = calculate_sample_size(
        baseline_rate=baseline_rate,
        mde=mde,
        confidence_level=confidence_level,
        power=power,
        daily_traffic=daily_traffic,
    )
    return SampleSizeCalculatorResponse.model_validate(data)
