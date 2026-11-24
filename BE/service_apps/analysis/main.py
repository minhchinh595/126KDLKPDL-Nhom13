from fastapi import Depends, FastAPI

from app.analysis.correlation import build_correlation
from app.analysis.distribution import build_distribution
from app.analysis.seasonality import build_seasonality
from app.analysis.statistics import build_summary
from app.analysis.trends import build_trend
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

app = FastAPI(
    title="Electricity Analytics - Analysis Service",
    description="Internal stateless monthly electricity analysis service",
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
