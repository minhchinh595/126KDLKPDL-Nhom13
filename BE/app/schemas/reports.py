from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.analysis import CorrelationResponse, DistributionResponse, SeasonalityResponse, SummaryResponse, TrendResponse
from app.schemas.dashboard import DashboardOverview
from app.schemas.model_runs import ModelRunPublic


class ReportSummary(BaseModel):
    generated_at: datetime
    dashboard: DashboardOverview


class ReportAnalysis(BaseModel):
    unit: str
    start_month: str | None
    end_month: str | None
    summary: SummaryResponse
    trend: TrendResponse
    seasonality: SeasonalityResponse
    correlation: CorrelationResponse
    distribution: DistributionResponse


class ReportModelRuns(BaseModel):
    items: list[ModelRunPublic]
    limit: int
