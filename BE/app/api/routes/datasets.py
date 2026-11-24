import os
import re
import uuid
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
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
    return {"configured": bool(os.getenv("DATASET_SYNC_URL")), "latest_import": latest}


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
    if not file.filename or Path(file.filename).suffix.lower() != ".csv":
        raise HTTPException(status_code=415, detail="Only CSV uploads are supported")
    key = f"{uuid.uuid4()}.csv"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = _safe_storage_path(key)
    total = 0
    try:
        with path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="CSV exceeds the upload size limit")
                destination.write(chunk)
        _normalize_file(path)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    except ValueError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await file.close()
    dataset = Dataset(name=name.strip(), source=source.strip(), file_name=Path(file.filename).name[:255], storage_key=key, description=description, status="uploaded")
    db.add(dataset)
    try:
        db.commit()
        db.refresh(dataset)
    except IntegrityError as exc:
        db.rollback()
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="A dataset with this name and source already exists") from exc
    return dataset


@router.post("/{dataset_id}/import", response_model=ImportResult, dependencies=[Depends(require_admin)])
def import_dataset(dataset_id: int, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if not dataset.storage_key:
        raise HTTPException(status_code=409, detail="This dataset has no uploaded CSV file")
    path = _safe_storage_path(dataset.storage_key)
    try:
        normalized = _normalize_file(path)
    except HTTPException as exc:
        _record_failed_import(db, dataset, "upload", str(exc.detail))
        raise
    try:
        history = import_dataset_file(
            db, dataset, path, "upload", normalized_rows=normalized.rows
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"dataset": dataset, "history": history}


@router.post("/sync", response_model=ImportResult, dependencies=[Depends(require_admin)])
def sync_dataset(db: Session = Depends(get_db)):
    source_url = os.getenv("DATASET_SYNC_URL", "").strip()
    if not source_url:
        raise HTTPException(status_code=503, detail="DATASET_SYNC_URL is not configured")
    if not source_url.lower().startswith("https://"):
        raise HTTPException(status_code=422, detail="DATASET_SYNC_URL must use HTTPS")
    dataset = db.scalar(select(Dataset).where(Dataset.name == "Configured dataset sync", Dataset.source == source_url))
    if dataset is None:
        dataset = Dataset(name="Configured dataset sync", source=source_url, file_name="sync.csv", status="ready")
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
    key = f"{uuid.uuid4()}.csv"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = _safe_storage_path(key)
    request = Request(source_url, headers={"User-Agent": "ElectricityAnalytics/1.0"})
    total = 0
    try:
        with urlopen(request, timeout=20) as response, path.open("wb") as destination:
            if "text/csv" not in response.headers.get("Content-Type", "").lower() and "octet-stream" not in response.headers.get("Content-Type", "").lower():
                raise HTTPException(status_code=415, detail="Configured source did not return CSV content")
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Remote CSV exceeds the size limit")
                destination.write(chunk)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        path.unlink(missing_ok=True)
        dataset.status = "sync_failed"
        _record_failed_import(db, dataset, "sync", str(exc))
        raise HTTPException(status_code=502, detail="Dataset source could not be fetched or validated") from exc

    try:
        normalized = _normalize_file(path)
    except HTTPException as exc:
        path.unlink(missing_ok=True)
        if exc.status_code == 422:
            dataset.status = "sync_failed"
            _record_failed_import(db, dataset, "sync", str(exc.detail))
            raise HTTPException(
                status_code=502,
                detail="Dataset source could not be fetched or validated",
            ) from exc
        raise
    except Exception:
        path.unlink(missing_ok=True)
        raise
    dataset.storage_key = key
    db.commit()
    db.refresh(dataset)
    history = import_dataset_file(
        db, dataset, path, "sync", normalized_rows=normalized.rows
    )
    return {"dataset": dataset, "history": history}
