from datetime import datetime
from pydantic import BaseModel


class DashboardOverview(BaseModel):
    record_count: int
    start_month: str | None
    latest_month: str | None
    mean_demand_twh: float | None
    minimum_demand_twh: float | None
    maximum_demand_twh: float | None
    latest_demand_twh: float | None
    change_from_previous_month_pct: float | None
    dataset_count: int
    model_run_count: int
    data_updated_at: datetime | None
    unit: str
