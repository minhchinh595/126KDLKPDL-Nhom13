import logging
from typing import Any

from fastapi import Depends, FastAPI, HTTPException

from app.classification.model import classify_next_month, train_and_save_model
from app.classification.nem_classifier import classify_next_nem_day, train_nem_daily_classifier
from service_apps.classification.auth import require_classification_service_secret
from service_apps.classification.schemas import ClassificationRecordsRequest, NEMClassificationRequest


logger = logging.getLogger(__name__)

app = FastAPI(
    title="Electricity Analytics - Classification Service",
    description="Internal monthly electricity demand classification service",
    version="1.0.0",
)


def _records(payload: ClassificationRecordsRequest) -> list[dict]:
    return sorted(
        (record.model_dump() for record in payload.records),
        key=lambda record: record["month"],
    )


def _is_artifact_error(error: ValueError) -> bool:
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "artifact cannot be loaded",
            "artifact is incomplete or incompatible",
            "artifact uses an incompatible",
            "model is stale",
            "model was built from different source data",
        )
    )


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "success", "service": "classification"}


@app.post(
    "/internal/classification/train",
    dependencies=[Depends(require_classification_service_secret)],
    tags=["Internal Classification"],
)
def train_model(payload: ClassificationRecordsRequest) -> dict[str, Any]:
    records = _records(payload)
    logger.info("Classification training requested: records=%s", len(records))
    try:
        result = train_and_save_model(records)
        logger.info("Classification training completed")
        return result
    except ValueError as exc:
        logger.warning("Classification training rejected: %s", str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Could not write Classification model artifact")
        raise HTTPException(
            status_code=507,
            detail="Classification model artifact could not be saved",
        ) from exc
    except Exception as exc:
        logger.exception("Classification training failed")
        raise HTTPException(
            status_code=500,
            detail="Classification training could not be completed",
        ) from exc


@app.post(
    "/internal/classification/run",
    dependencies=[Depends(require_classification_service_secret)],
    tags=["Internal Classification"],
)
def run_model(payload: ClassificationRecordsRequest) -> dict[str, Any]:
    records = _records(payload)
    logger.info("Classification run requested: records=%s", len(records))
    try:
        result = classify_next_month(records)
        logger.info("Classification run completed")
        return result
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=409,
            detail="Classification artifact is missing. An Admin must train the model before running it.",
        ) from exc
    except ValueError as exc:
        logger.warning("Classification run rejected: %s", str(exc))
        if _is_artifact_error(exc):
            raise HTTPException(
                status_code=409,
                detail="Classification artifact is incompatible with the current data. An Admin must train the model again.",
            ) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Could not read Classification model artifact")
        raise HTTPException(
            status_code=500,
            detail="Classification model artifact could not be read",
        ) from exc
    except Exception as exc:
        logger.exception("Classification run failed")
        raise HTTPException(
            status_code=500,
            detail="Classification could not be completed",
        ) from exc


@app.post(
    "/internal/classification/nem/train",
    dependencies=[Depends(require_classification_service_secret)],
    tags=["Internal NEM Classification"],
)
def train_nem_model(payload: NEMClassificationRequest) -> dict[str, Any]:
    logger.info("NEM classification training requested: samples=%s", payload.training_sample_count)
    try:
        result = train_nem_daily_classifier(payload)
        logger.info("NEM classification training completed")
        return result
    except ValueError as exc:
        logger.warning("NEM classification training rejected: %s", str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Could not write NEM Classification artifact")
        raise HTTPException(status_code=507, detail="NEM Classification artifact could not be saved") from exc
    except Exception as exc:
        logger.exception("NEM classification training failed")
        raise HTTPException(status_code=500, detail="NEM classification training could not be completed") from exc


@app.post(
    "/internal/classification/nem/run",
    dependencies=[Depends(require_classification_service_secret)],
    tags=["Internal NEM Classification"],
)
def run_nem_model(payload: NEMClassificationRequest) -> dict[str, Any]:
    logger.info("NEM classification run requested: observations=%s", payload.observation_count)
    try:
        result = classify_next_nem_day(payload)
        logger.info("NEM classification run completed: forecast_date=%s", result["forecast_date"])
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail="NEM Classification artifact is missing. An Admin must train it first.") from exc
    except ValueError as exc:
        if "artifact" in str(exc).lower():
            raise HTTPException(status_code=409, detail="NEM Classification artifact is incompatible with current data") from exc
        logger.warning("NEM classification run rejected: %s", str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Could not read NEM Classification artifact")
        raise HTTPException(status_code=500, detail="NEM Classification artifact could not be read") from exc
    except Exception as exc:
        logger.exception("NEM classification run failed")
        raise HTTPException(status_code=500, detail="NEM classification could not be completed") from exc
