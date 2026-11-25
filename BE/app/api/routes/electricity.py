import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import require_analyst
from app.db.database import get_db
from app.db.models import NEMObservation
from app.schemas.nem import NEMObservationPublic, NEMObservationsResponse
from app.services.nem_data import NEMDatasetUnavailable, query_coverage, query_observations, resolve_nem_dataset

router = APIRouter()
DAILY_METRICS = {"demand", "price", "demand_energy", "generation_renewable", "renewable_proportion"}
VERIFIED_UNITS = {("demand", "5m"): "MW", ("demand", "1d"): "MW", ("price", "1d"): "$/MWh", ("demand_energy", "1d"): "MWh", ("generation_renewable", "1d"): "MW", ("renewable_proportion", "1d"): "%"}


def _read(metric: str, interval: str, start_at: datetime | None, end_at: datetime | None, page: int, page_size: int, db: Session):
    try:
        dataset, rows, total = query_observations(db, metric=metric, interval=interval, start_at=start_at, end_at=end_at, page=page, page_size=page_size)
        if interval == "1d" and metric not in DAILY_METRICS:
            raise ValueError("unsupported daily metric")
        return {
            "dataset_name": dataset.name, "network_code": "NEM", "metric": metric,
            "interval": interval, "unit": rows[0].unit if rows else VERIFIED_UNITS.get((metric, interval)),
            "timezone": "Australia/Brisbane", "page": page, "page_size": page_size,
            "total_matches": total, "coverage": query_coverage(db, metric, interval, start_at, end_at),
            "records": [NEMObservationPublic(id=row.id, dataset_name=dataset.name,
                network_code=row.network_code, metric=row.metric, interval=row.interval,
                unit=row.unit, observed_at=row.observed_at, value=float(row.value),
                result=row.result, grouping_type=row.grouping_type,
                grouping_code=row.grouping_code) for row in rows],
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except NEMDatasetUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="NEM observations are unavailable") from exc


@router.get("/electricity/observations", response_model=NEMObservationsResponse, dependencies=[Depends(require_analyst)])
def get_observations(
    metric: str = Query("demand"), interval: str = Query("1d"),
    start_at: datetime | None = None, end_at: datetime | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(500, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return _read(metric, interval, start_at, end_at, page, page_size, db)


# Existing public path retained. The response is now NEM observations; old
# VNM month/TWh fields are intentionally not fabricated.
@router.get("/electricity/demand", response_model=NEMObservationsResponse, dependencies=[Depends(require_analyst)])
def get_demand(
    start_at: datetime | None = None, end_at: datetime | None = None,
    interval: str = Query("1d"), page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1, le=1000), db: Session = Depends(get_db),
):
    return _read("demand", interval, start_at, end_at, page, page_size, db)


@router.get("/electricity/demand/statistics", dependencies=[Depends(require_analyst)])
def demand_statistics(start_at: datetime | None = None, end_at: datetime | None = None, interval: str = "1d", db: Session = Depends(get_db)):
    result = _read("demand", interval, start_at, end_at, 1, 1000, db)
    values = [row.value for row in result["records"]]
    page = 2
    while len(values) < result["total_matches"]:
        next_page = _read("demand", interval, start_at, end_at, page, 1000, db)
        values.extend(row.value for row in next_page["records"])
        page += 1
    return {"metric": "demand", "interval": interval, "unit": result["unit"], "count": result["total_matches"], "mean": sum(values)/len(values) if values else None, "minimum": min(values) if values else None, "maximum": max(values) if values else None, "coverage": result["coverage"]}


@router.get("/electricity/demand/{record_id:int}", dependencies=[Depends(require_analyst)])
def demand_detail(record_id: int, db: Session = Depends(get_db)):
    try:
        dataset = resolve_nem_dataset(db)
        row = db.scalar(select(NEMObservation).where(NEMObservation.id == record_id, NEMObservation.dataset_id == dataset.id, NEMObservation.metric == "demand", NEMObservation.grouping_type == "network", NEMObservation.grouping_code == ""))
    except NEMDatasetUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="NEM observations are unavailable") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="NEM demand observation not found")
    return NEMObservationPublic(id=row.id, dataset_name=dataset.name, network_code=row.network_code, metric=row.metric, interval=row.interval, unit=row.unit, observed_at=row.observed_at, value=float(row.value), result=row.result, grouping_type=row.grouping_type, grouping_code=row.grouping_code)


@router.get("/electricity/demand/export", dependencies=[Depends(require_analyst)])
def export_demand_csv(start_at: datetime | None = None, end_at: datetime | None = None, interval: str = "1d", page: int = Query(1, ge=1), page_size: int = Query(1000, ge=1, le=1000), db: Session = Depends(get_db)):
    result = _read("demand", interval, start_at, end_at, page, page_size, db)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["dataset_name", "network_code", "metric", "interval", "unit", "observed_at", "value", "result", "grouping_type", "grouping_code"])
    for row in result["records"]:
        writer.writerow([row.dataset_name, row.network_code, row.metric, row.interval, row.unit, row.observed_at.isoformat(), row.value, row.result, row.grouping_type, row.grouping_code])
    return Response(stream.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=nem_demand_observations.csv"})
