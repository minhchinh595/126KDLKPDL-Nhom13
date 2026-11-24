import logging
from typing import Any

from fastapi import Depends, FastAPI, HTTPException

from app.clustering.kmeans import (
    ArtifactCompatibilityError,
    build_clustering_result,
    train_and_save_model,
)
from service_apps.clustering.auth import require_clustering_service_secret
from service_apps.clustering.schemas import (
    ClusteringRunRequest,
    ClusteringTrainRequest,
)


logger = logging.getLogger(__name__)

app = FastAPI(
    title="Electricity Analytics - Clustering Service",
    description="Internal K-Means service for monthly electricity demand",
    version="1.0.0",
)


def _records(payload: ClusteringRunRequest) -> list[dict]:
    return sorted(
        (record.model_dump() for record in payload.records),
        key=lambda record: record["month"],
    )


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "success", "service": "clustering"}


@app.post(
    "/internal/clustering/train",
    dependencies=[Depends(require_clustering_service_secret)],
    tags=["Internal Clustering"],
)
def train_model(payload: ClusteringTrainRequest) -> dict[str, Any]:
    try:
        return train_and_save_model(_records(payload), max_k=payload.max_k)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Could not save Clustering model artifact")
        raise HTTPException(
            status_code=500,
            detail="Could not save the Clustering model artifact",
        ) from exc
    except Exception as exc:
        logger.exception("Clustering training failed")
        raise HTTPException(
            status_code=500,
            detail="Clustering training could not be completed",
        ) from exc


@app.post(
    "/internal/clustering/run",
    dependencies=[Depends(require_clustering_service_secret)],
    tags=["Internal Clustering"],
)
def run_model(payload: ClusteringRunRequest) -> dict[str, Any]:
    try:
        return build_clustering_result(_records(payload))
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=409,
            detail="Clustering artifact is missing. An Admin must train the model before running it.",
        ) from exc
    except ArtifactCompatibilityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Clustering artifact is incompatible with the current data. An Admin must train the model again.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Clustering run failed")
        raise HTTPException(
            status_code=500,
            detail="Clustering could not be completed",
        ) from exc
