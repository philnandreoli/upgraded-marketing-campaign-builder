from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.models.experiments import ExperimentStatus, MetricSource, StatMethod


class ExperimentConfigDTO(BaseModel):
    min_sample_size: int = Field(default=100, ge=1)
    confidence_threshold: float = Field(default=0.95, ge=0.5, le=0.9999)
    auto_winner_enabled: bool = False
    stat_method: StatMethod = StatMethod.BAYESIAN


class CreateExperimentRequest(BaseModel):
    variant_group: str
    name: str = Field(min_length=1, max_length=200)
    config: ExperimentConfigDTO = Field(default_factory=ExperimentConfigDTO)


class UpdateExperimentRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[ExperimentStatus] = None
    config: Optional[ExperimentConfigDTO] = None


class ExperimentResponse(BaseModel):
    id: str
    campaign_id: str
    workspace_id: str
    variant_group: str
    name: str
    status: ExperimentStatus
    config: ExperimentConfigDTO
    started_at: Optional[datetime] = None
    concluded_at: Optional[datetime] = None
    winner_variant: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RecordVariantMetricRequest(BaseModel):
    content_piece_index: int = Field(ge=0)
    variant: str = Field(min_length=1, max_length=32)
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    conversions: int = Field(default=0, ge=0)
    revenue: float = Field(default=0.0, ge=0.0)
    custom_metrics: dict = Field(default_factory=dict)
    source: MetricSource = MetricSource.MANUAL


class VariantMetricResponse(BaseModel):
    id: str
    experiment_id: str
    campaign_id: str
    content_piece_index: int
    variant: str
    impressions: int
    clicks: int
    conversions: int
    revenue: float
    custom_metrics: dict
    source: MetricSource
    recorded_at: datetime


class BulkImportMetricsRequest(BaseModel):
    metrics: list[RecordVariantMetricRequest] = Field(default_factory=list)
    csv_data: Optional[str] = None


class VariantComparisonItem(BaseModel):
    variant: str
    impressions: int
    clicks: int
    conversions: int
    revenue: float
    ctr: float
    conversion_rate: float


class ExperimentReportResponse(BaseModel):
    experiment_id: str
    campaign_id: str
    status: ExperimentStatus
    winner_variant: Optional[str] = None
    variants: list[VariantComparisonItem]
    pairwise_statistics: list[dict]


class SelectWinnerRequest(BaseModel):
    winner_variant: str = Field(min_length=1, max_length=32)


class ConcludeExperimentResponse(BaseModel):
    experiment: ExperimentResponse
    auto_selected_winner: Optional[str] = None


class ExportExperimentResponse(BaseModel):
    format: str
    content_type: str
    data: str


class ExperimentLearningRequest(BaseModel):
    experiment_id: str
    campaign_id: str
    summary: str = Field(min_length=1, max_length=5000)
    tags: list[str] = Field(default_factory=list)
    ai_generated: bool = False


class ExperimentLearningResponse(BaseModel):
    id: str
    experiment_id: str
    campaign_id: str
    workspace_id: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    ai_generated: bool = False
    created_at: datetime


class SampleSizeCalculatorResponse(BaseModel):
    sample_size_per_variant: int
    total_sample_size: int
    estimated_days: Optional[int] = None


class ExperimentForecastResponse(BaseModel):
    days_ahead: int
    variants: list[dict]


class ExperimentInsightsResponse(BaseModel):
    experiment_id: str
    campaign_id: str
    insights: dict
