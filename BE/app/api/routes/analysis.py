import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.analysis.correlation import build_correlation
from app.analysis.seasonality import build_seasonality
from app.analysis.statistics import build_summary
from app.analysis.trends import build_trend
from app.db.database import get_db
from app.db.models import ElectricityConsumption

router = APIRouter()


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


@router.get("/analysis/summary")
def get_summary(
    start_month: str | None = None,
    end_month: str | None = None,
    db: Session = Depends(get_db),
):
    records = _get_records_or_raise(db, start_month, end_month)
    return {
        "unit": "TWh",
        "start_month": records[0]["month"] if records else None,
        "end_month": records[-1]["month"] if records else None,
        **build_summary(records),
    }


@router.get("/analysis/trend")
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
    return {
        "unit": "TWh",
        **build_trend(records, window_months=window_months),
    }


@router.get("/analysis/seasonality")
def get_seasonality(
    start_month: str | None = None,
    end_month: str | None = None,
    db: Session = Depends(get_db),
):
    records = _get_records_or_raise(db, start_month, end_month)
    return {
        "unit": "TWh",
        **build_seasonality(records),
    }


@router.get("/analysis/correlation")
def get_correlation(
    start_month: str | None = None,
    end_month: str | None = None,
    db: Session = Depends(get_db),
):
    records = _get_records_or_raise(db, start_month, end_month)
    return {
        "unit": "TWh",
        **build_correlation(records),
    }


@router.get("/analysis/distribution")
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
    values = [record["value"] for record in records]

    if not values:
        return {
            "unit": "TWh",
            "count": 0,
            "bins": [],
        }

    minimum = min(values)
    maximum = max(values)

    if minimum == maximum:
        return {
            "unit": "TWh",
            "count": len(values),
            "bins": [{
                "start": minimum,
                "end": maximum,
                "count": len(values),
            }],
        }

    width = (maximum - minimum) / bins
    histogram = []

    for index in range(bins):
        bin_start = minimum + index * width
        bin_end = maximum if index == bins - 1 else minimum + (index + 1) * width

        if index == bins - 1:
            count = sum(
                bin_start <= value <= bin_end
                for value in values
            )
        else:
            count = sum(
                bin_start <= value < bin_end
                for value in values
            )

        histogram.append({
            "start": round(bin_start, 4),
            "end": round(bin_end, 4),
            "count": count,
        })

    return {
        "unit": "TWh",
        "count": len(values),
        "bins": histogram,
    }