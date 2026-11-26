import os
import re
from datetime import datetime, timezone
from math import ceil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin, require_analyst
from app.clients.ingestion import (
    IngestionFileTooLarge,
    IngestionServiceRejected,
    IngestionServiceUnavailable,
    NormalizedCSV,
    ingestion_service_client,
)
from app.db.database import get_db
from app.db.models import Dataset, DatasetImport
from app.schemas.datasets import DatasetListResponse, DatasetPublic, ImportHistoryPublic, ImportResult, SyncStatus
from app.services.dataset_import import import_dataset_file

router = APIRouter(prefix="/datasets", dependencies=[Depends(require_analyst)])
MAX_UPLOAD_BYTES = int(os.getenv("DATASET_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
UPLOAD_DIR = Path(os.getenv("DATASET_UPLOAD_DIR", str(Path(__file__).resolve().parents[3] / "uploads"))).resolve()
CSV_INGESTION_DISABLED_DETAIL = (
    "CSV dataset ingestion is disabled. Open Electricity NEM is the only active data source."
)


def _safe_storage_path(key: str) -> Path:
    if not re.fullmatch(r"[0-9a-f-]{36}\.csv", key):
        raise HTTPException(status_code=404, detail="Uploaded dataset file was not found")
    path = (UPLOAD_DIR / key).resolve()
    if path.parent != UPLOAD_DIR:
        raise HTTPException(status_code=404, detail="Uploaded dataset file was not found")
    return path


def _normalize_file(path: Path) -> NormalizedCSV:
    try:
        return ingestion_service_client.normalize(path.read_bytes())
    except IngestionServiceRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IngestionFileTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except IngestionServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Ingestion Service is unavailable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _record_failed_import(db: Session, dataset: Dataset, mode: str, error: str) -> None:
    db.add(DatasetImport(
        dataset_id=dataset.id,
        mode=mode,
        status="failed",
        error_count=1,
        error_message=error[:2000],
        completed_at=datetime.now(timezone.utc),
    ))
    db.commit()


@router.get("", response_model=DatasetListResponse)
def list_datasets(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=255), db: Session = Depends(get_db),
):
    statement, count_statement = select(Dataset), select(func.count()).select_from(Dataset)
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(Dataset.name.ilike(pattern) | Dataset.source.ilike(pattern))
        count_statement = count_statement.where(Dataset.name.ilike(pattern) | Dataset.source.ilike(pattern))
    total = db.scalar(count_statement) or 0
    items = db.scalars(statement.order_by(Dataset.created_at.desc(), Dataset.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": items, "page": page, "page_size": page_size, "total": total, "pages": ceil(total / page_size)}


@router.get("/sync/status", response_model=SyncStatus)
def sync_status(db: Session = Depends(get_db)):
    latest = db.scalar(
        select(DatasetImport).where(DatasetImport.mode == "sync").order_by(DatasetImport.started_at.desc()).limit(1)
    )
    return {"configured": False, "latest_import": latest}


@router.get("/{dataset_id}/history", response_model=list[ImportHistoryPublic])
def dataset_history(dataset_id: int, db: Session = Depends(get_db)):
    if db.get(Dataset, dataset_id) is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return db.scalars(select(DatasetImport).where(DatasetImport.dataset_id == dataset_id).order_by(DatasetImport.started_at.desc())).all()


@router.get("/{dataset_id}", response_model=DatasetPublic)
def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


@router.post("/upload", response_model=DatasetPublic, status_code=201, dependencies=[Depends(require_admin)])
async def upload_dataset(
    file: UploadFile = File(...), name: str = Form(min_length=2, max_length=160),
    source: str = Form(min_length=2, max_length=255), description: str | None = Form(None),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=410, detail=CSV_INGESTION_DISABLED_DETAIL)


@router.post("/{dataset_id}/import", response_model=ImportResult, dependencies=[Depends(require_admin)])
def import_dataset(dataset_id: int, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    raise HTTPException(status_code=410, detail=CSV_INGESTION_DISABLED_DETAIL)


@router.post("/sync", response_model=ImportResult, dependencies=[Depends(require_admin)])
def sync_dataset(db: Session = Depends(get_db)):
    raise HTTPException(status_code=410, detail=CSV_INGESTION_DISABLED_DETAIL)
