from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.clients.classification import (
    ClassificationArtifactWriteError,
    ClassificationServiceConflict,
    ClassificationServiceError,
    ClassificationServiceRejected,
    ClassificationServiceUnavailable,
    classification_service_client,
)
from app.db.database import get_db
from app.db.models import ElectricityConsumption, ModelRun
from app.api.dependencies import require_admin, require_analyst
from app.services.nem_data import NEMDatasetUnavailable
from app.services.nem_ml_data import NEMMLDataError, build_nem_prediction_payload, load_nem_daily_demand
from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE
from app.services.nem_model_runs import nem_h2_model_run_filter
from app.services.nem_ml_contract import NEM_FEATURE_SCHEMA_VERSION, NEM_FORECAST_HORIZON_DAYS, nem_forecast_dates
from app.services.model_provenance import ModelProvenanceError, merge_training_model_provenance
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


def _load_nem_classification_payload(db: Session) -> dict:
    return build_nem_prediction_payload(load_nem_daily_demand(db))


def _require_forecast_ready(payload: dict) -> None:
    if payload.get("forecast_status") == "ready" and isinstance(payload.get("forecast"), dict):
        return
    raise HTTPException(
        status_code=409,
        detail={
            "forecast_status": "not_ready",
            "message": payload.get("forecast_message") or "NEM daily demand is not complete through the required cutoff date",
            "as_of_date": payload.get("as_of_date"),
            "cutoff_date": payload.get("cutoff_date"),
            "forecast_date": payload.get("forecast_date"),
            "last_observed_date": payload.get("last_observed_date"),
        },
    )


def _nem_provenance(payload: dict) -> dict:
    return {
        "dataset_id": payload["dataset_id"],
        "dataset_name": payload["dataset_name"],
        "dataset_source": payload["dataset_source"],
        "network_code": payload["network_code"],
        "metric": payload["metric"],
        "interval": payload["interval"],
        "unit": payload["unit"],
        "feature_names": payload["feature_names"],
        "feature_units": payload["feature_units"],
        "observation_start": payload["observation_start"],
        "observation_end": payload["observation_end"],
        "observation_count": payload["observation_count"],
        "training_start": payload["training_start"],
        "training_end": payload["training_end"],
        "training_sample_count": payload["training_sample_count"],
        "excluded_sample_count": payload["excluded_sample_count"],
        "exclusion_reasons": payload["exclusion_reasons"],
        "missing_dates": payload["missing_dates"],
        "data_fingerprint": payload["data_fingerprint"],
        "horizon_days": payload["horizon_days"],
        "feature_schema_version": payload["feature_schema_version"],
        "forecast_date": payload["forecast_date"],
        "cutoff_date": payload["cutoff_date"],
    }


def _nem_training_provenance(payload: dict, result: dict) -> dict:
    try:
        provenance = merge_training_model_provenance(
            _nem_provenance(payload), result.get("model_provenance"),
            expected_model_type="classification",
        )
    except ModelProvenanceError as exc:
        raise ClassificationServiceUnavailable("Classification Service returned invalid model metadata") from exc
    result.pop("model_provenance", None)
    return provenance


def _failed_run_provenance(payload: dict | None) -> dict | None:
    """Return H2 provenance only when the loaded payload proves the full identity."""
    if not isinstance(payload, dict):
        return None
    try:
        provenance = _nem_provenance(payload)
    except (KeyError, TypeError):
        return None
    expected = {
        "dataset_name": NEM_DATASET_NAME,
        "dataset_source": NEM_DATASET_SOURCE,
        "network_code": "NEM",
        "metric": "demand",
        "interval": "1d",
        "unit": "MW",
        "horizon_days": NEM_FORECAST_HORIZON_DAYS,
        "feature_schema_version": NEM_FEATURE_SCHEMA_VERSION,
    }
    dataset_id = provenance.get("dataset_id")
    if any(provenance.get(key) != value for key, value in expected.items()):
        return None
    if isinstance(dataset_id, bool) or not isinstance(dataset_id, int) or dataset_id < 1:
        return None
    return provenance


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
            **({"window_months": result["window_months"]} if "window_months" in result else {}),
            **({"provenance": result.pop("_provenance")} if "_provenance" in result else {}),
        },
        metrics=result,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _save_failed_run(
    db: Session,
    *,
    stage: str,
    started_at: datetime,
    error: str,
    provenance: dict | None = None,
) -> None:
    db.add(ModelRun(
        model_type="classification", status="failed", started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        parameters={"stage": stage, **({"provenance": provenance} if provenance is not None else {})},
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
    payload: dict | None = None

    try:
        payload = _load_nem_classification_payload(db)
        result = classification_service_client.train_nem(payload)
        result["_provenance"] = _nem_training_provenance(payload, result)
        run = _save_run(
            db,
            result=result,
            started_at=started_at,
        )
        return _serialize_run(run)

    except ValueError as exc:
        db.rollback()
        _save_failed_run(db, stage="training", started_at=started_at, error=str(exc), provenance=_failed_run_provenance(payload))
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except ClassificationServiceRejected as exc:
        db.rollback()
        _save_failed_run(db, stage="training", started_at=started_at, error=str(exc), provenance=_failed_run_provenance(payload))
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except ClassificationServiceConflict as exc:
        db.rollback()
        _save_failed_run(db, stage="training", started_at=started_at, error=str(exc), provenance=_failed_run_provenance(payload))
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    except ClassificationArtifactWriteError as exc:
        db.rollback()
        _save_failed_run(db, stage="training", started_at=started_at, error=str(exc), provenance=_failed_run_provenance(payload))
        raise HTTPException(
            status_code=500,
            detail="Could not save the classification model artifact",
        ) from exc

    except ClassificationServiceUnavailable as exc:
        db.rollback()
        _save_failed_run(db, stage="training", started_at=started_at, error=str(exc), provenance=_failed_run_provenance(payload))
        raise HTTPException(status_code=503, detail="Classification Service is unavailable") from exc

    except NEMDatasetUnavailable as exc:
        db.rollback()
        _save_failed_run(db, stage="training", started_at=started_at, error="Open Electricity NEM dataset is unavailable", provenance=_failed_run_provenance(payload))
        raise HTTPException(status_code=503, detail="Open Electricity NEM dataset is unavailable") from exc

    except ClassificationServiceError as exc:
        db.rollback()
        _save_failed_run(db, stage="training", started_at=started_at, error=str(exc), provenance=_failed_run_provenance(payload))
        raise HTTPException(
            status_code=500,
            detail="Classification Service could not complete training",
        ) from exc

    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Classification data or run history is unavailable in PostgreSQL",
        ) from exc

    except OSError as exc:
        db.rollback()
        _save_failed_run(db, stage="training", started_at=started_at, error="Could not save model artifact", provenance=_failed_run_provenance(payload))
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
    payload: dict | None = None

    try:
        payload = _load_nem_classification_payload(db)
        _require_forecast_ready(payload)
        result = classification_service_client.run_nem(payload)
        result["_provenance"] = _nem_provenance(payload)
        run = _save_run(
            db,
            result=result,
            started_at=started_at,
        )
        return _serialize_run(run)

    except FileNotFoundError as exc:
        db.rollback()
        _save_failed_run(db, stage="forecast", started_at=started_at, error=str(exc), provenance=_failed_run_provenance(payload))
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    except ClassificationServiceConflict as exc:
        db.rollback()
        _save_failed_run(db, stage="forecast", started_at=started_at, error=str(exc), provenance=_failed_run_provenance(payload))
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    except ClassificationServiceRejected as exc:
        db.rollback()
        _save_failed_run(db, stage="forecast", started_at=started_at, error=str(exc), provenance=_failed_run_provenance(payload))
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except ClassificationServiceUnavailable as exc:
        db.rollback()
        _save_failed_run(db, stage="forecast", started_at=started_at, error=str(exc), provenance=_failed_run_provenance(payload))
        raise HTTPException(status_code=503, detail="Classification Service is unavailable") from exc

    except ClassificationServiceError as exc:
        db.rollback()
        _save_failed_run(db, stage="forecast", started_at=started_at, error=str(exc), provenance=_failed_run_provenance(payload))
        raise HTTPException(
            status_code=500,
            detail="Classification Service could not complete the run",
        ) from exc

    except NEMDatasetUnavailable as exc:
        db.rollback()
        _save_failed_run(db, stage="forecast", started_at=started_at, error="Open Electricity NEM dataset is unavailable", provenance=_failed_run_provenance(payload))
        raise HTTPException(status_code=503, detail="Open Electricity NEM dataset is unavailable") from exc

    except NEMMLDataError as exc:
        db.rollback()
        _save_failed_run(db, stage="forecast", started_at=started_at, error=str(exc), provenance=_failed_run_provenance(payload))
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except ValueError as exc:
        db.rollback()
        _save_failed_run(db, stage="forecast", started_at=started_at, error=str(exc), provenance=_failed_run_provenance(payload))
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
    _, cutoff_date, forecast_date = nem_forecast_dates()
    statement = (
        select(ModelRun)
        .where(
            nem_h2_model_run_filter("classification"),
            ModelRun.status == "completed",
            ModelRun.metrics["stage"].astext == "forecast",
            ModelRun.metrics["cutoff_date"].astext == cutoff_date.isoformat(),
            ModelRun.metrics["forecast_date"].astext == forecast_date.isoformat(),
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
    nem_filter = nem_h2_model_run_filter("classification")
    count = db.scalar(select(func.count()).select_from(ModelRun).where(nem_filter)) or 0
    rows = db.scalars(select(ModelRun).where(nem_filter).order_by(ModelRun.created_at.desc(), ModelRun.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_serialize_run(row) for row in rows], "page": page, "page_size": page_size, "total": count, "pages": ceil(count / page_size)}


@router.get("/classification/runs/{run_id}", response_model=ModelRunPublic, dependencies=[Depends(require_analyst)])
def get_classification_run(
    run_id: int,
    db: Session = Depends(get_db),
):
    statement = select(ModelRun).where(
        ModelRun.id == run_id,
        nem_h2_model_run_filter("classification"),
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
