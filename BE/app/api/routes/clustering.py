from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.clustering.kmeans import build_clustering_result
from app.db.database import get_db
from app.db.models import ElectricityConsumption, ModelRun

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


@router.post("/clustering/run")
def run_clustering(
    max_k: int = Query(default=5, ge=2, le=8),
    db: Session = Depends(get_db),
):
    run = ModelRun(
        model_type="clustering",
        status="running",
        started_at=datetime.now(timezone.utc),
        parameters={
            "max_k": max_k,
            "candidate_k_min": 2,
            "selection_method": "highest_silhouette_score",
            "features": [
                "demand",
                "previous_month_change_pct",
                "previous_year_change_pct",
            ],
            "scaling": "StandardScaler",
        },
    )
    db.add(run)

    try:
        db.flush()

        records = _load_demand_records(db)
        result = build_clustering_result(records, max_k=max_k)

        run.status = "completed"
        run.metrics = result
        run.completed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(run)
        return _serialize_run(run)

    except ValueError as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = datetime.now(timezone.utc)

        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()

        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Clustering data or run history is unavailable in PostgreSQL",
        ) from exc

    except Exception as exc:
        run.status = "failed"
        run.error_message = "Unexpected clustering error"
        run.completed_at = datetime.now(timezone.utc)

        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Clustering could not be completed",
        ) from exc


@router.get("/clustering/latest")
def get_latest_clustering(
    db: Session = Depends(get_db),
):
    statement = (
        select(ModelRun)
        .where(
            ModelRun.model_type == "clustering",
            ModelRun.status == "completed",
        )
        .order_by(ModelRun.created_at.desc(), ModelRun.id.desc())
        .limit(1)
    )

    try:
        run = db.execute(statement).scalar_one_or_none()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Clustering run history is unavailable in PostgreSQL",
        ) from exc

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="No completed clustering run was found",
        )

    return _serialize_run(run)


@router.get("/clustering/runs/{run_id}")
def get_clustering_run(
    run_id: int,
    db: Session = Depends(get_db),
):
    statement = select(ModelRun).where(
        ModelRun.id == run_id,
        ModelRun.model_type == "clustering",
    )

    try:
        run = db.execute(statement).scalar_one_or_none()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Clustering run history is unavailable in PostgreSQL",
        ) from exc

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="Clustering run was not found",
        )

    return _serialize_run(run)