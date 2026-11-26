from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.clients.clustering import (
    ClusteringServiceConflict,
    ClusteringServiceRejected,
    ClusteringServiceUnavailable,
    clustering_service_client,
)
from app.db.database import get_db
from app.db.models import ElectricityConsumption, ModelRun
from app.api.dependencies import require_admin, require_analyst
from app.services.nem_data import NEMDatasetUnavailable
from app.services.nem_ml_data import NEMMLDataError, load_nem_clustering_input
from app.services.nem_model_runs import nem_model_run_filter
from app.services.model_provenance import ModelProvenanceError, merge_training_model_provenance
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


def _load_nem_clustering_payload(db: Session) -> dict:
    return load_nem_clustering_input(db).as_service_payload()


def _nem_provenance(payload: dict) -> dict:
    return {
        "dataset_name": payload["dataset_name"],
        "dataset_source": payload["dataset_source"],
        "dataset_id": payload["dataset_id"],
        "network_code": payload["network_code"],
        "interval": payload["interval"],
        "feature_configurations": {
            name: {
                "feature_names": config["feature_names"],
                "feature_units": config["feature_units"],
                "training_start": config["start_date"],
                "training_end": config["end_date"],
                "observation_count": config["observation_count"],
                "data_fingerprint": config["data_fingerprint"],
                "dropped_date_count": config["dropped_date_count"],
                "dropped_reasons": config["dropped_reasons"],
                "metric_quality": config["metric_quality"],
            }
            for name, config in payload["configurations"].items()
        },
    }


def _nem_training_provenance(payload: dict, result: dict) -> dict:
    try:
        provenance = merge_training_model_provenance(
            _nem_provenance(payload), result.get("model_provenance"),
            expected_model_type="clustering",
        )
    except ModelProvenanceError as exc:
        raise ClusteringServiceUnavailable("Clustering Service returned invalid model metadata") from exc
    result.pop("model_provenance", None)
    return provenance


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


def _save_failed_training(db: Session, *, started_at: datetime, error: str) -> None:
    db.add(ModelRun(
        model_type="clustering",
        status="failed",
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        parameters={"stage": "training"},
        error_message=error[:2000],
    ))
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()


@router.post("/clustering/train", response_model=ModelRunPublic)
def train_clustering_model(
    max_k: int = Query(default=5, ge=2, le=5),
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    started_at = datetime.now(timezone.utc)
    try:
        payload = _load_nem_clustering_payload(db)
        result = clustering_service_client.train_nem(payload, max_k=max_k)
        provenance = _nem_training_provenance(payload, result)
        run = ModelRun(
            model_type="clustering", status="completed", started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            parameters={"stage": "training", "max_k": max_k, "provenance": provenance}, metrics=result,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return _serialize_run(run)
    except ClusteringServiceRejected as exc:
        db.rollback()
        _save_failed_training(db, started_at=started_at, error=str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ClusteringServiceConflict as exc:
        db.rollback()
        _save_failed_training(db, started_at=started_at, error=str(exc))
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ClusteringServiceUnavailable as exc:
        db.rollback()
        _save_failed_training(db, started_at=started_at, error=str(exc))
        raise HTTPException(status_code=503, detail="Clustering Service is unavailable") from exc
    except NEMDatasetUnavailable as exc:
        db.rollback()
        _save_failed_training(db, started_at=started_at, error="Open Electricity NEM dataset is unavailable")
        raise HTTPException(status_code=503, detail="Open Electricity NEM dataset is unavailable") from exc
    except NEMMLDataError as exc:
        db.rollback()
        _save_failed_training(db, started_at=started_at, error=str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Clustering data or run history is unavailable in PostgreSQL") from exc
    except Exception as exc:
        db.rollback()
        _save_failed_training(db, started_at=started_at, error="Unexpected Clustering Service error")
        raise HTTPException(status_code=500, detail="Clustering training could not be completed") from exc


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

        payload = _load_nem_clustering_payload(db)
        run.parameters = {"stage": "run", "provenance": _nem_provenance(payload)}
        result = clustering_service_client.run_nem(payload)

        run.status = "completed"
        run.metrics = result
        run.completed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(run)
        return _serialize_run(run)

    except ClusteringServiceConflict as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    except ClusteringServiceRejected as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except ClusteringServiceUnavailable as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        raise HTTPException(status_code=503, detail="Clustering Service is unavailable") from exc

    except NEMDatasetUnavailable as exc:
        run.status = "failed"
        run.error_message = "Open Electricity NEM dataset is unavailable"
        run.completed_at = datetime.now(timezone.utc)
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        raise HTTPException(status_code=503, detail="Open Electricity NEM dataset is unavailable") from exc

    except NEMMLDataError as exc:
        run.status = "failed"
        run.error_message = str(exc)[:2000]
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


@router.get("/clustering/latest", response_model=ModelRunPublic, dependencies=[Depends(require_analyst)])
def get_latest_clustering(
    db: Session = Depends(get_db),
):
    statement = (
        select(ModelRun)
        .where(
            nem_model_run_filter("clustering"),
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
    nem_filter = nem_model_run_filter("clustering")
    count = db.scalar(select(func.count()).select_from(ModelRun).where(nem_filter)) or 0
    rows = db.scalars(select(ModelRun).where(nem_filter).order_by(ModelRun.created_at.desc(), ModelRun.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_serialize_run(row) for row in rows], "page": page, "page_size": page_size, "total": count, "pages": ceil(count / page_size)}


@router.get("/clustering/runs/{run_id}", response_model=ModelRunPublic, dependencies=[Depends(require_analyst)])
def get_clustering_run(
    run_id: int,
    db: Session = Depends(get_db),
):
    statement = select(ModelRun).where(
        ModelRun.id == run_id,
        nem_model_run_filter("clustering"),
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
