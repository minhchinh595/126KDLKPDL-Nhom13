from typing import Literal

import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.dependencies import require_analyst
from app.db.models import ElectricityConsumption
from app.services.electricity import load_demand_from_db

router = APIRouter()


class DemandRecord(BaseModel):
    id: int
    month: str
    value: float = Field(ge=0, allow_inf_nan=False)


class DemandResponse(BaseModel):
    source: str
    country: str
    iso3: Literal["VNM"]
    unit: Literal["TWh"]
    total: int
    start_month: str | None
    end_month: str | None
    records: list[DemandRecord]
    page: int = 1
    page_size: int = 100
    total_matches: int = 0


class DemandStatistics(BaseModel):
    count: int
    mean: float | None
    minimum: float | None
    maximum: float | None
    start_month: str | None
    end_month: str | None


@router.get("/electricity/demand", response_model=DemandResponse, dependencies=[Depends(require_analyst)])
def get_demand(
    response: Response,
    start_month: str | None = None,
    end_month: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Return monthly Vietnam electricity demand stored in PostgreSQL."""
    response.headers["Cache-Control"] = "no-store"

    try:
        return load_demand_from_db(
            db,
            start_month=start_month,
            end_month=end_month,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Electricity data is unavailable in PostgreSQL",
        ) from exc


@router.get("/electricity/demand/statistics", response_model=DemandStatistics, dependencies=[Depends(require_analyst)])
def demand_statistics(
    start_month: str | None = None,
    end_month: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        data = load_demand_from_db(db, start_month=start_month, end_month=end_month, page_size=0)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Electricity data is unavailable in PostgreSQL") from exc
    values = [row["value"] for row in data["records"]]
    return {
        "count": data["total"],
        "mean": round(sum(values) / len(values), 4) if values else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "start_month": data["start_month"],
        "end_month": data["end_month"],
    }


@router.get("/electricity/demand/{record_id:int}", dependencies=[Depends(require_analyst)])
def demand_detail(record_id: int, db: Session = Depends(get_db)):
    row = db.execute(select(ElectricityConsumption).where(
        ElectricityConsumption.id == record_id,
        ElectricityConsumption.iso3 == "VNM",
        ElectricityConsumption.metric == "demand",
        ElectricityConsumption.fuel.is_(None),
        ElectricityConsumption.unit == "TWh",
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Demand record not found")
    return {
        "id": row.id, "month": row.month.strftime("%Y-%m"), "value": float(row.value),
        "country": row.country, "iso3": row.iso3, "metric": row.metric, "unit": row.unit,
    }


@router.get("/electricity/demand/export", dependencies=[Depends(require_analyst)])
def export_demand_csv(start_month: str | None = None, end_month: str | None = None, db: Session = Depends(get_db)):
    try:
        data = load_demand_from_db(db, start_month=start_month, end_month=end_month, page_size=0)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Electricity data is unavailable in PostgreSQL") from exc
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["country", "iso3", "month", "metric", "value", "unit"])
    for row in data["records"]:
        writer.writerow([data["country"], data["iso3"], row["month"], "demand", row["value"], data["unit"]])
    return Response(stream.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=electricity_demand.csv"})
