from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import ElectricityConsumption, ModelRun
from app.prediction.model import forecast_next_month, train_and_save_model

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
    stage: str,
    result: dict,
    started_at: datetime,
) -> ModelRun:
    run = ModelRun(
        model_type="prediction",
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


@router.post("/prediction/train")
def train_prediction_model(
    db: Session = Depends(get_db),
):
    started_at = datetime.now(timezone.utc)

    try:
        records = _load_demand_records(db)
        result = train_and_save_model(records)
        run = _save_run(
            db,
            stage="training",
            result=result,
            started_at=started_at,
        )
        return _serialize_run(run)

    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Prediction data or run history is unavailable in PostgreSQL",
        ) from exc

    except OSError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not save the prediction model artifact",
        ) from exc


@router.post("/prediction/run")
def run_prediction(
    db: Session = Depends(get_db),
):
    started_at = datetime.now(timezone.utc)

    try:
        records = _load_demand_records(db)
        result = forecast_next_month(records)
        run = _save_run(
            db,
            stage="forecast",
            result=result,
            started_at=started_at,
        )
        return _serialize_run(run)

    except FileNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Prediction data or run history is unavailable in PostgreSQL",
        ) from exc


@router.get("/prediction/latest")
def get_latest_prediction(
    db: Session = Depends(get_db),
):
    statement = (
        select(ModelRun)
        .where(
            ModelRun.model_type == "prediction",
            ModelRun.status == "completed",
        )
        .order_by(ModelRun.created_at.desc(), ModelRun.id.desc())
    )

    try:
        runs = db.execute(statement).scalars().all()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Prediction run history is unavailable in PostgreSQL",
        ) from exc

    latest_forecast = next(
        (
            run
            for run in runs
            if run.metrics and run.metrics.get("stage") == "forecast"
        ),
        None,
    )

    if latest_forecast is None:
        raise HTTPException(
            status_code=404,
            detail="No completed prediction was found",
        )

    return _serialize_run(latest_forecast)


@router.get("/prediction/runs/{run_id}")
def get_prediction_run(
    run_id: int,
    db: Session = Depends(get_db),
):
    statement = select(ModelRun).where(
        ModelRun.id == run_id,
        ModelRun.model_type == "prediction",
    )

    try:
        run = db.execute(statement).scalar_one_or_none()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Prediction run history is unavailable in PostgreSQL",
        ) from exc

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="Prediction run was not found",
        )

    return _serialize_run(run)