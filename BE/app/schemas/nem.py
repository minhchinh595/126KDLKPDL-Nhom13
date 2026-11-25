from datetime import datetime
from pydantic import BaseModel


class NEMObservationPublic(BaseModel):
    id: int
    dataset_name: str
    network_code: str
    metric: str
    interval: str
    unit: str
    observed_at: datetime
    value: float
    result: str
    grouping_type: str
    grouping_code: str
    timezone: str = "Australia/Brisbane"


class NEMObservationsResponse(BaseModel):
    dataset_name: str
    network_code: str
    metric: str
    interval: str
    unit: str | None
    timezone: str
    page: int
    page_size: int
    total_matches: int
    coverage: dict
    records: list[NEMObservationPublic]


class NEMDashboardOverview(BaseModel):
    dataset_name: str
    dataset_status: str
    total_observations: int
    latest_daily_demand_mw: float | None
    average_daily_demand_mw: float | None
    minimum_daily_demand_mw: float | None
    maximum_daily_demand_mw: float | None
    latest_renewable_proportion_percent: float | None
    latest_price_per_mwh: float | None
    latest_data_timestamp: datetime | None
    timezone: str = "Australia/Brisbane"
