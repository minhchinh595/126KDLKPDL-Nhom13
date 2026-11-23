from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.classification.model import (
    classify_next_month,
    train_and_save_model,
)
from app.db.database import get_db
from app.db.models import ElectricityConsumption, ModelRun
from app.api.dependencies import require_admin, require_analyst
from fastapi import Query
from sqlalchemy import func
from math import ceil
from app.schemas.model_runs import ModelRunListResponse, ModelRunPublic

router = APIRouter()


def _load_demand_records(db: Session) -> list[dict]:
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

    rows = db.execute(statement).all()

    return [
        {
            "month": row.month.strftime("%Y-%m"),
            "value": float(row.value),
        }
        for row in rows
    ]


def _save_run(
    db: Session,
    *,
    result: dict,
    started_at: datetime,
) -> ModelRun:
    stage = result["stage"]

    run = ModelRun(
        model_type="classification",
        status="completed",
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        parameters={
            "stage": stage,
            "model_name": result["model_name"],
            "window_months": result["window_months"],
        },
        metrics=result,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _save_failed_run(db: Session, *, stage: str, started_at: datetime, error: str) -> None:
    db.add(ModelRun(
        model_type="classification", status="failed", started_at=started_at,
        completed_at=datetime.now(timezone.utc), parameters={"stage": stage},
        error_message=error[:2000],
    ))
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()


def _serialize_run(run: ModelRun) -> dict:
    return {
        "id": run.id,
        "model_type": run.model_type,
        "status": run.status,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "parameters": run.parameters,
        "metrics": run.metrics,
        "error_message": run.error_message,
    }


@router.post("/classification/train", response_model=ModelRunPublic)
def train_classification_model(
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    started_at = datetime.now(timezone.utc)

    try:
        records = _load_demand_records(db)
        result = train_and_save_model(records)
        run = _save_run(
            db,
            result=result,
            started_at=started_at,
        )
        return _serialize_run(run)

    except ValueError as exc:
        db.rollback()
        _save_failed_run(db, stage="training", started_at=started_at, error=str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Classification data or run history is unavailable in PostgreSQL",
        ) from exc

    except OSError as exc:
        db.rollback()
        _save_failed_run(db, stage="training", started_at=started_at, error="Could not save model artifact")
        raise HTTPException(
            status_code=500,
            detail="Could not save the classification model artifact",
        ) from exc


@router.post("/classification/run", response_model=ModelRunPublic)
def run_classification(
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    started_at = datetime.now(timezone.utc)

    try:
        records = _load_demand_records(db)
        result = classify_next_month(records)
        run = _save_run(
            db,
            result=result,
            started_at=started_at,
        )
        return _serialize_run(run)

    except FileNotFoundError as exc:
        db.rollback()
        _save_failed_run(db, stage="forecast", started_at=started_at, error=str(exc))
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    except ValueError as exc:
        db.rollback()
        _save_failed_run(db, stage="forecast", started_at=started_at, error=str(exc))
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Classification data or run history is unavailable in PostgreSQL",
        ) from exc


@router.get("/classification/latest", response_model=ModelRunPublic, dependencies=[Depends(require_analyst)])
def get_latest_classification(
    db: Session = Depends(get_db),
):
    statement = (
        select(ModelRun)
        .where(
            ModelRun.model_type == "classification",
            ModelRun.status == "completed",
            ModelRun.metrics["stage"].astext == "forecast",
        )
        .order_by(ModelRun.created_at.desc(), ModelRun.id.desc())
        .limit(1)
    )

    try:
        latest_forecast = db.execute(statement).scalar_one_or_none()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Classification run history is unavailable in PostgreSQL",
        ) from exc

    if latest_forecast is None:
        raise HTTPException(
            status_code=404,
            detail="No completed classification was found",
        )

    return _serialize_run(latest_forecast)


@router.get("/classification/runs", response_model=ModelRunListResponse, dependencies=[Depends(require_analyst)])
def list_classification_runs(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count()).select_from(ModelRun).where(ModelRun.model_type == "classification")) or 0
    rows = db.scalars(select(ModelRun).where(ModelRun.model_type == "classification").order_by(ModelRun.created_at.desc(), ModelRun.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_serialize_run(row) for row in rows], "page": page, "page_size": page_size, "total": count, "pages": ceil(count / page_size)}


@router.get("/classification/runs/{run_id}", response_model=ModelRunPublic, dependencies=[Depends(require_analyst)])
def get_classification_run(
    run_id: int,
    db: Session = Depends(get_db),
):
    statement = select(ModelRun).where(
        ModelRun.id == run_id,
        ModelRun.model_type == "classification",
    )

    try:
        run = db.execute(statement).scalar_one_or_none()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Classification run history is unavailable in PostgreSQL",
        ) from exc

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="Classification run was not found",
        )

    return _serialize_run(run)
