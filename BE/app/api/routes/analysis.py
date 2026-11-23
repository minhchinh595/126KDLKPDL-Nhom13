import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.clients.analysis import AnalysisServiceRejected, AnalysisServiceUnavailable, analysis_service_client
from app.db.database import get_db
from app.db.models import ElectricityConsumption
from app.api.dependencies import require_analyst
from app.schemas.analysis import (
    CorrelationResponse,
    DistributionResponse,
    SeasonalityResponse,
    SummaryResponse,
    TrendResponse,
)

router = APIRouter(dependencies=[Depends(require_analyst)])


def _parse_month(value: str | None, parameter_name: str) -> date | None:
    if value is None:
        return None

    if not re.fullmatch(r"[1-9]\d{3}-(0[1-9]|1[0-2])", value):
        raise HTTPException(
            status_code=422,
            detail=f"{parameter_name} must use YYYY-MM format",
        )

    return date.fromisoformat(f"{value}-01")


def _load_records(
    db: Session,
    start_month: str | None,
    end_month: str | None,
) -> list[dict]:
    start_date = _parse_month(start_month, "start_month")
    end_date = _parse_month(end_month, "end_month")

    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_month must be before or equal to end_month",
        )

    statement = (
        select(
            ElectricityConsumption.month,
            ElectricityConsumption.value,
        )
        .where(
            ElectricityConsumption.iso3 == "VNM",
            ElectricityConsumption.metric == "demand",
            ElectricityConsumption.fuel.is_(None),
            ElectricityConsumption.unit == "TWh",
        )
        .order_by(ElectricityConsumption.month)
    )

    if start_date is not None:
        statement = statement.where(
            ElectricityConsumption.month >= start_date
        )

    if end_date is not None:
        statement = statement.where(
            ElectricityConsumption.month <= end_date
        )

    rows = db.execute(statement).all()

    return [
        {
            "month": row.month.strftime("%Y-%m"),
            "value": float(row.value),
        }
        for row in rows
    ]


def _get_records_or_raise(
    db: Session,
    start_month: str | None,
    end_month: str | None,
) -> list[dict]:
    try:
        return _load_records(db, start_month, end_month)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Electricity data is unavailable in PostgreSQL",
        ) from exc


def _analyze(operation: str, records: list[dict], **options) -> dict:
    try:
        return analysis_service_client.analyze(operation, records, **options)
    except AnalysisServiceRejected as exc:
        raise HTTPException(status_code=422, detail="Analysis service rejected the request") from exc
    except AnalysisServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Analysis service is unavailable") from exc


@router.get("/analysis/summary", response_model=SummaryResponse)
def get_summary(
    start_month: str | None = None,
    end_month: str | None = None,
    db: Session = Depends(get_db),
):
    records = _get_records_or_raise(db, start_month, end_month)
    return _analyze("summary", records)


@router.get("/analysis/trend", response_model=TrendResponse)
def get_trend(
    start_month: str | None = None,
    end_month: str | None = None,
    window_months: int = 12,
    db: Session = Depends(get_db),
):
    if not 2 <= window_months <= 36:
        raise HTTPException(
            status_code=422,
            detail="window_months must be between 2 and 36",
        )

    records = _get_records_or_raise(db, start_month, end_month)
    return _analyze("trend", records, window_months=window_months)


@router.get("/analysis/seasonality", response_model=SeasonalityResponse)
def get_seasonality(
    start_month: str | None = None,
    end_month: str | None = None,
    db: Session = Depends(get_db),
):
    records = _get_records_or_raise(db, start_month, end_month)
    return _analyze("seasonality", records)


@router.get("/analysis/correlation", response_model=CorrelationResponse)
def get_correlation(
    start_month: str | None = None,
    end_month: str | None = None,
    db: Session = Depends(get_db),
):
    records = _get_records_or_raise(db, start_month, end_month)
    return _analyze("correlation", records)


@router.get("/analysis/distribution", response_model=DistributionResponse)
def get_distribution(
    start_month: str | None = None,
    end_month: str | None = None,
    bins: int = 10,
    db: Session = Depends(get_db),
):
    if not 2 <= bins <= 50:
        raise HTTPException(
            status_code=422,
            detail="bins must be between 2 and 50",
        )

    records = _get_records_or_raise(db, start_month, end_month)
    return _analyze("distribution", records, bins=bins)
