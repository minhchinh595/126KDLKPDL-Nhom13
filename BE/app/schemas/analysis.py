from pydantic import BaseModel


class SummaryResponse(BaseModel):
    unit: str
    start_month: str | None
    end_month: str | None
    count: int
    mean: float | None
    median: float | None
    min: float | None
    max: float | None


class TrendPoint(BaseModel):
    month: str
    value: float
    trend: float | None


class TrendResponse(BaseModel):
    unit: str
    window_months: int
    method: str
    records: list[TrendPoint]


class SeasonalityMonth(BaseModel):
    month_number: int
    count: int
    mean: float | None
    median: float | None
    min: float | None
    max: float | None


class SeasonalityResponse(BaseModel):
    unit: str
    method: str
    records: list[SeasonalityMonth]


class CorrelationResponse(BaseModel):
    unit: str
    method: str
    features: list[str]
    matrix: dict[str, dict[str, float | None]]
    pair_counts: dict[str, dict[str, int]]


class DistributionBin(BaseModel):
    start: float
    end: float
    count: int


class DistributionResponse(BaseModel):
    unit: str
    count: int
    bins: list[DistributionBin]
