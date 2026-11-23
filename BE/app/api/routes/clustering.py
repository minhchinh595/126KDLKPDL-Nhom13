from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.clustering.kmeans import ArtifactCompatibilityError, build_clustering_result, train_and_save_model
from app.db.database import get_db
from app.db.models import ElectricityConsumption, ModelRun
from app.api.dependencies import require_admin, require_analyst
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


@router.post("/clustering/train", response_model=ModelRunPublic)
def train_clustering_model(
    max_k: int = Query(default=5, ge=2, le=8),
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    started_at = datetime.now(timezone.utc)
    try:
        result = train_and_save_model(_load_demand_records(db), max_k=max_k)
        run = ModelRun(
            model_type="clustering", status="completed", started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            parameters={"stage": "training", "max_k": max_k}, metrics=result,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return _serialize_run(run)
    except ValueError as exc:
        db.rollback()
        failed = ModelRun(model_type="clustering", status="failed", started_at=started_at,
                          completed_at=datetime.now(timezone.utc), parameters={"stage": "training"},
                          error_message=str(exc)[:2000])
        db.add(failed)
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        db.rollback()
        failed = ModelRun(model_type="clustering", status="failed", started_at=started_at,
                          completed_at=datetime.now(timezone.utc), parameters={"stage": "training"},
                          error_message="Could not save the clustering model artifact")
        db.add(failed)
        db.commit()
        raise HTTPException(status_code=500, detail="Could not save the clustering model artifact") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Clustering data or run history is unavailable in PostgreSQL") from exc


@router.post("/clustering/run", response_model=ModelRunPublic)
def run_clustering(
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    run = ModelRun(
        model_type="clustering",
        status="running",
        started_at=datetime.now(timezone.utc),
        parameters={
            "stage": "run",
        },
    )
    db.add(run)

    try:
        db.flush()

        records = _load_demand_records(db)
        result = build_clustering_result(records)

        run.status = "completed"
        run.metrics = result
        run.completed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(run)
        return _serialize_run(run)

    except ArtifactCompatibilityError as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    except ValueError as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = datetime.now(timezone.utc)

        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()

        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except FileNotFoundError as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

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


@router.get("/clustering/latest", response_model=ModelRunPublic, dependencies=[Depends(require_analyst)])
def get_latest_clustering(
    db: Session = Depends(get_db),
):
    statement = (
        select(ModelRun)
        .where(
            ModelRun.model_type == "clustering",
            ModelRun.status == "completed",
            ModelRun.metrics["stage"].astext == "run",
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


@router.get("/clustering/runs", response_model=ModelRunListResponse, dependencies=[Depends(require_analyst)])
def list_clustering_runs(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count()).select_from(ModelRun).where(ModelRun.model_type == "clustering")) or 0
    rows = db.scalars(select(ModelRun).where(ModelRun.model_type == "clustering").order_by(ModelRun.created_at.desc(), ModelRun.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_serialize_run(row) for row in rows], "page": page, "page_size": page_size, "total": count, "pages": ceil(count / page_size)}


@router.get("/clustering/runs/{run_id}", response_model=ModelRunPublic, dependencies=[Depends(require_analyst)])
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
