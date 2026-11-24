import logging
import os

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status

from app.ingestion.pipeline import normalize_csv
from service_apps.ingestion.auth import require_ingestion_service_secret
from service_apps.ingestion.schemas import NormalizeResponse


logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = int(os.getenv("DATASET_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
if MAX_UPLOAD_BYTES <= 0:
    raise RuntimeError("DATASET_MAX_UPLOAD_BYTES must be greater than zero")

app = FastAPI(
    title="Electricity Analytics - Data Ingestion Service",
    description="Internal monthly CSV validation and normalization service",
    version="1.0.0",
)


async def _read_limited_csv(file: UploadFile) -> bytes:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Only CSV uploads are supported")
    chunks = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="CSV exceeds the upload size limit")
        chunks.append(chunk)
    return b"".join(chunks)


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "success", "service": "ingestion"}


@app.post(
    "/internal/ingestion/normalize",
    response_model=NormalizeResponse,
    dependencies=[Depends(require_ingestion_service_secret)],
    tags=["Internal Ingestion"],
)
async def normalize_upload(file: UploadFile = File(...)) -> dict:
    try:
        content = await _read_limited_csv(file)
        normalized = normalize_csv(content)
        logger.info(
            "CSV normalization completed: rows=%s, bytes=%s",
            normalized["rows_read"],
            len(content),
        )
        return normalized
    except HTTPException:
        raise
    except (ValueError, UnicodeError) as exc:
        logger.info("CSV normalization rejected")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("CSV normalization failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CSV normalization could not be completed",
        ) from exc
    finally:
        await file.close()
