from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ExperimentStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    CONCLUDED = "concluded"
    ARCHIVED = "archived"


class StatMethod(str, Enum):
    BAYESIAN = "bayesian"
    FREQUENTIST = "frequentist"


class MetricSource(str, Enum):
    MANUAL = "manual"
    CSV = "csv"
    WEBHOOK = "webhook"
    API = "api"


class ExperimentConfig(BaseModel):
    min_sample_size: int = Field(default=100, ge=1)
    confidence_threshold: float = Field(default=0.95, ge=0.5, le=0.9999)
    auto_winner_enabled: bool = Field(default=False)
    stat_method: StatMethod = Field(default=StatMethod.BAYESIAN)


class Experiment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str
    workspace_id: str
    variant_group: str
    name: str
    status: ExperimentStatus = ExperimentStatus.DRAFT
    config: ExperimentConfig = Field(default_factory=ExperimentConfig)
    started_at: Optional[datetime] = None
    concluded_at: Optional[datetime] = None
    winner_variant: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class VariantMetric(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    experiment_id: str
    campaign_id: str
    content_piece_index: int
    variant: str
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    conversions: int = Field(default=0, ge=0)
    revenue: float = Field(default=0.0, ge=0.0)
    custom_metrics: dict = Field(default_factory=dict)
    source: MetricSource = MetricSource.MANUAL
    recorded_at: datetime = Field(default_factory=datetime.utcnow)


class ExperimentLearning(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    experiment_id: str
    campaign_id: str
    workspace_id: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    ai_generated: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
