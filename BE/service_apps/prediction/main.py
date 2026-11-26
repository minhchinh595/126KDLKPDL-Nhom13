import logging
from typing import Any

from fastapi import Depends, FastAPI, HTTPException

from app.prediction.model import forecast_next_month, train_and_save_model
from app.prediction.nem_model import run_nem_daily_forecast, train_nem_daily_model
from service_apps.prediction.auth import require_prediction_service_secret
from service_apps.prediction.schemas import NEMPredictionRequest, PredictionRecordsRequest


logger = logging.getLogger(__name__)

app = FastAPI(
    title="Electricity Analytics - Prediction Service",
    description="Internal monthly electricity demand prediction service",
    version="1.0.0",
)


def _records(payload: PredictionRecordsRequest) -> list[dict]:
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
    return {"status": "success", "service": "prediction"}


@app.post(
    "/internal/prediction/train",
    dependencies=[Depends(require_prediction_service_secret)],
    tags=["Internal Prediction"],
)
def train_model(payload: PredictionRecordsRequest) -> dict[str, Any]:
    records = _records(payload)
    logger.info("Prediction training requested: records=%s", len(records))
    try:
        result = train_and_save_model(records)
        logger.info("Prediction training completed")
        return result
    except ValueError as exc:
        logger.warning("Prediction training rejected: %s", str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Could not write Prediction model artifact")
        raise HTTPException(
            status_code=507,
            detail="Prediction model artifact could not be saved",
        ) from exc
    except Exception as exc:
        logger.exception("Prediction training failed")
        raise HTTPException(
            status_code=500,
            detail="Prediction training could not be completed",
        ) from exc


@app.post(
    "/internal/prediction/run",
    dependencies=[Depends(require_prediction_service_secret)],
    tags=["Internal Prediction"],
)
def run_model(payload: PredictionRecordsRequest) -> dict[str, Any]:
    records = _records(payload)
    logger.info("Prediction run requested: records=%s", len(records))
    try:
        result = forecast_next_month(records)
        logger.info("Prediction run completed")
        return result
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=409,
            detail="Prediction artifact is missing. An Admin must train the model before running it.",
        ) from exc
    except ValueError as exc:
        if _is_artifact_error(exc):
            raise HTTPException(
                status_code=409,
                detail="Prediction artifact is incompatible with the current data. An Admin must train the model again.",
            ) from exc
        logger.warning("Prediction run rejected: %s", str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Could not read Prediction model artifact")
        raise HTTPException(
            status_code=500,
            detail="Prediction model artifact could not be read",
        ) from exc
    except Exception as exc:
        logger.exception("Prediction run failed")
        raise HTTPException(
            status_code=500,
            detail="Prediction could not be completed",
        ) from exc


@app.post(
    "/internal/prediction/nem/train",
    dependencies=[Depends(require_prediction_service_secret)],
    tags=["Internal NEM Prediction"],
)
def train_nem_model(payload: NEMPredictionRequest) -> dict[str, Any]:
    logger.info("NEM prediction training requested: samples=%s", payload.training_sample_count)
    try:
        result = train_nem_daily_model(payload)
        logger.info("NEM prediction training completed")
        return result
    except ValueError as exc:
        logger.warning("NEM prediction training rejected: %s", str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Could not write NEM Prediction artifact")
        raise HTTPException(status_code=507, detail="NEM Prediction artifact could not be saved") from exc
    except Exception as exc:
        logger.exception("NEM prediction training failed")
        raise HTTPException(status_code=500, detail="NEM prediction training could not be completed") from exc


@app.post(
    "/internal/prediction/nem/run",
    dependencies=[Depends(require_prediction_service_secret)],
    tags=["Internal NEM Prediction"],
)
def run_nem_model(payload: NEMPredictionRequest) -> dict[str, Any]:
    logger.info("NEM prediction run requested: observations=%s", payload.observation_count)
    try:
        result = run_nem_daily_forecast(payload)
        logger.info("NEM prediction run completed: forecast_date=%s", result["forecast_date"])
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail="NEM Prediction artifact is missing. An Admin must train it first.") from exc
    except ValueError as exc:
        if "artifact" in str(exc).lower():
            raise HTTPException(status_code=409, detail="NEM Prediction artifact is incompatible with the current data") from exc
        logger.warning("NEM prediction run rejected: %s", str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Could not read NEM Prediction artifact")
        raise HTTPException(status_code=500, detail="NEM Prediction artifact could not be read") from exc
    except Exception as exc:
        logger.exception("NEM prediction run failed")
        raise HTTPException(status_code=500, detail="NEM prediction could not be completed") from exc
