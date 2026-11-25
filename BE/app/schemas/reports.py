from datetime import datetime
from pydantic import BaseModel

from app.schemas.dashboard import DashboardOverview
from app.schemas.model_runs import ModelRunPublic


class ReportSummary(BaseModel):
    generated_at: datetime
    dashboard: DashboardOverview


class ReportAnalysis(BaseModel):
    dataset_name: str
    timezone: str
    start_at: datetime | None
    end_at: datetime | None
    summary: dict
    trend: dict
    seasonality: dict
    correlation: dict
    distribution: dict


class ReportModelRuns(BaseModel):
    items: list[ModelRunPublic]
    limit: int
