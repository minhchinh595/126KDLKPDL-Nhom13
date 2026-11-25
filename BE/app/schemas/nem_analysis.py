from pydantic import BaseModel


class NEMSummaryResponse(BaseModel):
    metric: str
    interval: str
    unit: str
    sample_count: int
    start_date: str | None
    end_date: str | None
    mean: float | None
    median: float | None
    minimum: float | None
    maximum: float | None


class NEMTrendPoint(BaseModel):
    period: str
    value: float | None
    sample_count: int
    weighted_sample_count: int | None = None
    expected_days: int
    coverage_fraction: float | None


class NEMTrendResponse(BaseModel):
    metric: str
    unit: str
    view: str
    aggregation: str
    records: list[NEMTrendPoint]


class NEMSeasonalityPoint(BaseModel):
    weekday: int
    count: int
    mean: float | None


class NEMSeasonalityResponse(BaseModel):
    metric: str
    unit: str
    method: str
    limitation: str
    records: list[NEMSeasonalityPoint]


class NEMMetricMetadata(BaseModel):
    unit: str | None


class NEMCorrelationResponse(BaseModel):
    metrics: dict[str, NEMMetricMetadata]
    alignment: str
    sample_dates: int
    matrix: dict[str, dict[str, float | None]]
    pair_counts: dict[str, dict[str, int]]


class NEMDistributionBin(BaseModel):
    start: float
    end: float
    count: int


class NEMDistributionResponse(BaseModel):
    metric: str
    interval: str
    unit: str | None
    sample_count: int
    bins: list[NEMDistributionBin]


class NEMScatterMetric(BaseModel):
    metric: str
    unit: str | None = None
    interval: str | None = None


class NEMScatterPoint(BaseModel):
    date: str
    x: float
    y: float


class NEMScatterResponse(BaseModel):
    x: NEMScatterMetric
    y: NEMScatterMetric
    sample_count: int
    points: list[NEMScatterPoint]
