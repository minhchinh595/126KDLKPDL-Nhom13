from fastapi import Depends, FastAPI, HTTPException

from app.analysis.correlation import build_correlation
from app.analysis.distribution import build_distribution
from app.analysis.seasonality import build_seasonality
from app.analysis.statistics import build_summary
from app.analysis.trends import build_trend
from app.analysis.nem import correlation as nem_correlation, distribution as nem_distribution, scatter as nem_scatter, seasonality as nem_seasonality, summary as nem_summary, trend as nem_trend
from app.schemas.analysis import (
    CorrelationResponse,
    DistributionResponse,
    SeasonalityResponse,
    SummaryResponse,
    TrendResponse,
)
from service_apps.analysis.auth import require_analysis_service_secret
from service_apps.analysis.schemas import (
    AnalysisRecordsRequest,
    DistributionRequest,
    TrendRequest,
)
from service_apps.analysis.nem_schemas import NEMDistributionRequest, NEMRecordsRequest, NEMScatterRequest, NEMTrendRequest
from zoneinfo import ZoneInfo

app = FastAPI(
    title="Electricity Analytics - Analysis Service",
    description="Internal stateless NEM descriptive analysis with legacy monthly operations",
    version="1.0.0",
)


def _records(payload: AnalysisRecordsRequest) -> list[dict]:
    return sorted(
        (record.model_dump() for record in payload.records),
        key=lambda record: record["month"],
    )


@app.get("/health", tags=["Health"])
def health_check() -> dict:
    return {"status": "success", "service": "analysis"}


@app.post(
    "/internal/analysis/summary",
    response_model=SummaryResponse,
    dependencies=[Depends(require_analysis_service_secret)],
    tags=["Internal Analysis"],
)
def summary(payload: AnalysisRecordsRequest) -> dict:
    records = _records(payload)
    return {
        "unit": "TWh",
        "start_month": records[0]["month"] if records else None,
        "end_month": records[-1]["month"] if records else None,
        **build_summary(records),
    }


@app.post(
    "/internal/analysis/trend",
    response_model=TrendResponse,
    dependencies=[Depends(require_analysis_service_secret)],
    tags=["Internal Analysis"],
)
def trend(payload: TrendRequest) -> dict:
    return {
        "unit": "TWh",
        **build_trend(_records(payload), window_months=payload.window_months),
    }


@app.post(
    "/internal/analysis/seasonality",
    response_model=SeasonalityResponse,
    dependencies=[Depends(require_analysis_service_secret)],
    tags=["Internal Analysis"],
)
def seasonality(payload: AnalysisRecordsRequest) -> dict:
    return {"unit": "TWh", **build_seasonality(_records(payload))}


@app.post(
    "/internal/analysis/correlation",
    response_model=CorrelationResponse,
    dependencies=[Depends(require_analysis_service_secret)],
    tags=["Internal Analysis"],
)
def correlation(payload: AnalysisRecordsRequest) -> dict:
    return {"unit": "TWh", **build_correlation(_records(payload))}


@app.post(
    "/internal/analysis/distribution",
    response_model=DistributionResponse,
    dependencies=[Depends(require_analysis_service_secret)],
    tags=["Internal Analysis"],
)
def distribution(payload: DistributionRequest) -> dict:
    return {"unit": "TWh", **build_distribution(_records(payload), bins=payload.bins)}


def _nem_records(payload: NEMRecordsRequest, *, allow_five_minute: bool = False) -> list[dict]:
    records = [record.model_dump() for record in payload.records]
    daily_keys = set()
    units = {}
    for record in records:
        observed_at = record["observed_at"]
        record["observed_at"] = record["observed_at"].isoformat()
        valid_interval = record["interval"] == "1d" or (allow_five_minute and record["metric"] == "demand" and record["interval"] == "5m")
        if not valid_interval or record["grouping_type"] != "network" or record["grouping_code"]:
            raise HTTPException(status_code=422, detail="NEM descriptive analysis requires supported network-level observations")
        if record["metric"] in units and units[record["metric"]] != record["unit"]:
            raise HTTPException(status_code=422, detail="NEM metric series contains inconsistent units")
        units[record["metric"]] = record["unit"]
        if record["interval"] == "1d":
            key = (record["metric"], observed_at.astimezone(ZoneInfo("Australia/Brisbane")).date())
            if key in daily_keys:
                raise HTTPException(status_code=422, detail="multiple daily series exist for the same metric and NEM-local date")
            daily_keys.add(key)
    return records


@app.post("/internal/analysis/nem/summary", dependencies=[Depends(require_analysis_service_secret)])
def nem_summary_endpoint(payload: NEMRecordsRequest) -> dict:
    return nem_summary(_nem_records(payload))


@app.post("/internal/analysis/nem/trend", dependencies=[Depends(require_analysis_service_secret)])
def nem_trend_endpoint(payload: NEMTrendRequest) -> dict:
    return nem_trend(_nem_records(payload), payload.view, payload.metric)


@app.post("/internal/analysis/nem/seasonality", dependencies=[Depends(require_analysis_service_secret)])
def nem_seasonality_endpoint(payload: NEMRecordsRequest) -> dict:
    return nem_seasonality(_nem_records(payload))


@app.post("/internal/analysis/nem/correlation", dependencies=[Depends(require_analysis_service_secret)])
def nem_correlation_endpoint(payload: NEMRecordsRequest) -> dict:
    return nem_correlation(_nem_records(payload))


@app.post("/internal/analysis/nem/distribution", dependencies=[Depends(require_analysis_service_secret)])
def nem_distribution_endpoint(payload: NEMDistributionRequest) -> dict:
    return nem_distribution(_nem_records(payload, allow_five_minute=True), payload.metric, payload.interval, payload.bins)


@app.post("/internal/analysis/nem/scatter", dependencies=[Depends(require_analysis_service_secret)])
def nem_scatter_endpoint(payload: NEMScatterRequest) -> dict:
    return nem_scatter(_nem_records(payload), payload.x_metric, payload.y_metric)
