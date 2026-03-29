"""PostgreSQL-backed experiment store."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import delete as sa_delete, select, update as sa_update

from backend.infrastructure.database import (
    ExperimentLearningRow,
    ExperimentRow,
    VariantMetricRow,
    async_session,
)
from backend.models.experiments import Experiment, ExperimentLearning, VariantMetric


class ExperimentStore:
    """Repository for experiments, variant metrics, and experiment learnings."""

    async def create_experiment(self, experiment: Experiment) -> Experiment:
        row = ExperimentRow(
            id=experiment.id,
            campaign_id=experiment.campaign_id,
            workspace_id=experiment.workspace_id,
            variant_group=experiment.variant_group,
            name=experiment.name,
            status=experiment.status.value,
            config=experiment.config.model_dump(),
            started_at=experiment.started_at,
            concluded_at=experiment.concluded_at,
            winner_variant=experiment.winner_variant,
            created_at=experiment.created_at,
            updated_at=experiment.updated_at,
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
        return experiment

    async def list_experiments_by_campaign(self, campaign_id: str) -> list[Experiment]:
        async with async_session() as session:
            result = await session.execute(
                select(ExperimentRow)
                .where(ExperimentRow.campaign_id == campaign_id)
                .order_by(ExperimentRow.created_at.desc())
            )
            return [_experiment_row_to_model(row) for row in result.scalars().all()]

    async def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        async with async_session() as session:
            row = await session.get(ExperimentRow, experiment_id)
            if row is None:
                return None
            return _experiment_row_to_model(row)

    async def update_experiment(
        self,
        experiment_id: str,
        *,
        name: Optional[str] = None,
        status: Optional[str] = None,
        config: Optional[dict] = None,
        started_at: Optional[datetime] = None,
        concluded_at: Optional[datetime] = None,
        winner_variant: Optional[str] = None,
    ) -> Experiment:
        values: dict[str, object] = {"updated_at": datetime.utcnow()}
        if name is not None:
            values["name"] = name
        if status is not None:
            values["status"] = status
        if config is not None:
            values["config"] = config
        if started_at is not None:
            values["started_at"] = started_at
        if concluded_at is not None:
            values["concluded_at"] = concluded_at
        if winner_variant is not None:
            values["winner_variant"] = winner_variant

        async with async_session() as session:
            result = await session.execute(
                sa_update(ExperimentRow)
                .where(ExperimentRow.id == experiment_id)
                .values(**values)
                .returning(ExperimentRow)
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise ValueError(f"Experiment {experiment_id!r} not found")
            await session.commit()
            return _experiment_row_to_model(row)

    async def create_variant_metric(self, metric: VariantMetric) -> VariantMetric:
        row = VariantMetricRow(
            id=metric.id,
            experiment_id=metric.experiment_id,
            campaign_id=metric.campaign_id,
            content_piece_index=metric.content_piece_index,
            variant=metric.variant,
            impressions=metric.impressions,
            clicks=metric.clicks,
            conversions=metric.conversions,
            revenue=metric.revenue,
            custom_metrics=metric.custom_metrics,
            source=metric.source.value,
            recorded_at=metric.recorded_at,
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
        return metric

    async def bulk_create_variant_metrics(self, metrics: list[VariantMetric]) -> list[VariantMetric]:
        if not metrics:
            return []
        rows = [
            VariantMetricRow(
                id=metric.id,
                experiment_id=metric.experiment_id,
                campaign_id=metric.campaign_id,
                content_piece_index=metric.content_piece_index,
                variant=metric.variant,
                impressions=metric.impressions,
                clicks=metric.clicks,
                conversions=metric.conversions,
                revenue=metric.revenue,
                custom_metrics=metric.custom_metrics,
                source=metric.source.value,
                recorded_at=metric.recorded_at,
            )
            for metric in metrics
        ]
        async with async_session() as session:
            session.add_all(rows)
            await session.commit()
        return metrics

    async def list_variant_metrics(self, experiment_id: str) -> list[VariantMetric]:
        async with async_session() as session:
            result = await session.execute(
                select(VariantMetricRow)
                .where(VariantMetricRow.experiment_id == experiment_id)
                .order_by(VariantMetricRow.recorded_at.desc())
            )
            return [_metric_row_to_model(row) for row in result.scalars().all()]

    async def delete_variant_metrics(self, experiment_id: str) -> int:
        async with async_session() as session:
            result = await session.execute(
                sa_delete(VariantMetricRow).where(VariantMetricRow.experiment_id == experiment_id)
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def create_learning(self, learning: ExperimentLearning) -> ExperimentLearning:
        row = ExperimentLearningRow(
            id=learning.id,
            experiment_id=learning.experiment_id,
            campaign_id=learning.campaign_id,
            workspace_id=learning.workspace_id,
            summary=learning.summary,
            tags=learning.tags,
            ai_generated=learning.ai_generated,
            created_at=learning.created_at,
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
        return learning

    async def list_learnings_by_workspace(self, workspace_id: str) -> list[ExperimentLearning]:
        async with async_session() as session:
            result = await session.execute(
                select(ExperimentLearningRow)
                .where(ExperimentLearningRow.workspace_id == workspace_id)
                .order_by(ExperimentLearningRow.created_at.desc())
            )
            return [_learning_row_to_model(row) for row in result.scalars().all()]


def _experiment_row_to_model(row: ExperimentRow) -> Experiment:
    return Experiment(
        id=row.id,
        campaign_id=row.campaign_id,
        workspace_id=row.workspace_id,
        variant_group=row.variant_group,
        name=row.name,
        status=row.status,
        config=row.config or {},
        started_at=row.started_at,
        concluded_at=row.concluded_at,
        winner_variant=row.winner_variant,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _metric_row_to_model(row: VariantMetricRow) -> VariantMetric:
    return VariantMetric(
        id=row.id,
        experiment_id=row.experiment_id,
        campaign_id=row.campaign_id,
        content_piece_index=row.content_piece_index,
        variant=row.variant,
        impressions=row.impressions,
        clicks=row.clicks,
        conversions=row.conversions,
        revenue=float(row.revenue),
        custom_metrics=row.custom_metrics or {},
        source=row.source,
        recorded_at=row.recorded_at,
    )


def _learning_row_to_model(row: ExperimentLearningRow) -> ExperimentLearning:
    return ExperimentLearning(
        id=row.id,
        experiment_id=row.experiment_id,
        campaign_id=row.campaign_id,
        workspace_id=row.workspace_id,
        summary=row.summary,
        tags=row.tags or [],
        ai_generated=row.ai_generated,
        created_at=row.created_at,
    )


_experiment_store: ExperimentStore | None = None


def get_experiment_store() -> ExperimentStore:
    global _experiment_store
    if _experiment_store is None:
        _experiment_store = ExperimentStore()
    return _experiment_store
