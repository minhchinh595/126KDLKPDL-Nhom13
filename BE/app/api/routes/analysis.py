from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import require_analyst
from app.clients.analysis import AnalysisServiceRejected, AnalysisServiceUnavailable, analysis_service_client
from app.db.database import get_db
from app.schemas.nem_analysis import NEMCorrelationResponse, NEMDistributionResponse, NEMScatterResponse, NEMSeasonalityResponse, NEMSummaryResponse, NEMTrendResponse
from app.services.nem_data import NEMDatasetUnavailable, query_observations

router = APIRouter(dependencies=[Depends(require_analyst)])
DAILY_METRICS = ("demand", "price", "demand_energy", "generation_renewable", "renewable_proportion")


def _load_daily_records(db: Session, start_at: datetime | None, end_at: datetime | None) -> list[dict]:
    records = []
    for metric in DAILY_METRICS:
        _, rows, total = query_observations(db, metric=metric, interval="1d", start_at=start_at, end_at=end_at, page=1, page_size=1000)
        records.extend({"metric": row.metric, "interval": row.interval, "observed_at": row.observed_at.isoformat(), "value": float(row.value), "unit": row.unit, "result": row.result, "grouping_type": row.grouping_type, "grouping_code": row.grouping_code} for row in rows)
        fetched = len(rows)
        page = 2
        while fetched < total:
            _, rows, _ = query_observations(db, metric=metric, interval="1d", start_at=start_at, end_at=end_at, page=page, page_size=1000)
            records.extend({"metric": row.metric, "interval": row.interval, "observed_at": row.observed_at.isoformat(), "value": float(row.value), "unit": row.unit, "result": row.result, "grouping_type": row.grouping_type, "grouping_code": row.grouping_code} for row in rows)
            fetched += len(rows)
            page += 1
    return records


def _analyze(operation: str, records: list[dict], **options) -> dict:
    try:
        return analysis_service_client.analyze(f"nem-{operation}", records, **options)
    except AnalysisServiceRejected as exc:
        raise HTTPException(status_code=422, detail="Analysis service rejected the request") from exc
    except AnalysisServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Analysis service is unavailable") from exc


def _records_or_raise(db: Session, start_at: datetime | None, end_at: datetime | None) -> list[dict]:
    try:
        if start_at and end_at and start_at.astimezone(timezone.utc) >= end_at.astimezone(timezone.utc):
            raise HTTPException(status_code=422, detail="start_at must be earlier than end_at")
        return _load_daily_records(db, start_at, end_at)
    except NEMDatasetUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="NEM observations are unavailable") from exc


@router.get("/analysis/summary", response_model=NEMSummaryResponse)
def get_summary(start_at: datetime | None = None, end_at: datetime | None = None, db: Session = Depends(get_db)):
    return _analyze("summary", _records_or_raise(db, start_at, end_at))


@router.get("/analysis/trend", response_model=NEMTrendResponse)
def get_trend(start_at: datetime | None = None, end_at: datetime | None = None, metric: str = "demand", view: str = Query("day", pattern="^(day|week|month)$"), db: Session = Depends(get_db)):
    return _analyze("trend", _records_or_raise(db, start_at, end_at), view=view, metric=metric)


@router.get("/analysis/seasonality", response_model=NEMSeasonalityResponse)
def get_seasonality(start_at: datetime | None = None, end_at: datetime | None = None, db: Session = Depends(get_db)):
    return _analyze("seasonality", _records_or_raise(db, start_at, end_at))


@router.get("/analysis/correlation", response_model=NEMCorrelationResponse)
def get_correlation(start_at: datetime | None = None, end_at: datetime | None = None, db: Session = Depends(get_db)):
    return _analyze("correlation", _records_or_raise(db, start_at, end_at))


@router.get("/analysis/distribution", response_model=NEMDistributionResponse)
def get_distribution(metric: str = "demand", interval: str = "1d", start_at: datetime | None = None, end_at: datetime | None = None, bins: int = Query(10, ge=2, le=50), db: Session = Depends(get_db)):
    try:
        _, rows, total = query_observations(db, metric=metric, interval=interval, start_at=start_at, end_at=end_at, page=1, page_size=1000)
        records = [{"metric": row.metric, "interval": row.interval, "observed_at": row.observed_at.isoformat(), "value": float(row.value), "unit": row.unit, "result": row.result, "grouping_type": row.grouping_type, "grouping_code": row.grouping_code} for row in rows]
        fetched = len(rows)
        page = 2
        while fetched < total:
            _, rows, _ = query_observations(db, metric=metric, interval=interval, start_at=start_at, end_at=end_at, page=page, page_size=1000)
            records.extend({"metric": row.metric, "interval": row.interval, "observed_at": row.observed_at.isoformat(), "value": float(row.value), "unit": row.unit, "result": row.result, "grouping_type": row.grouping_type, "grouping_code": row.grouping_code} for row in rows)
            fetched += len(rows)
            page += 1
        return _analyze("distribution", records, metric=metric, interval=interval, bins=bins)
    except NEMDatasetUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="NEM observations are unavailable") from exc


@router.get("/analysis/scatter", response_model=NEMScatterResponse)
def get_scatter(x_metric: str, y_metric: str, start_at: datetime | None = None, end_at: datetime | None = None, db: Session = Depends(get_db)):
    records = _records_or_raise(db, start_at, end_at)
    return _analyze("scatter", records, x_metric=x_metric, y_metric=y_metric)
