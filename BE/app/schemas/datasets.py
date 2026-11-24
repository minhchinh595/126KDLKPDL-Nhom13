from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class DatasetPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source: str
    file_name: str
    description: str | None
    record_count: int
    start_date: date | None
    end_date: date | None
    status: str
    created_at: datetime
    updated_at: datetime


class DatasetListResponse(BaseModel):
    items: list[DatasetPublic]
    page: int
    page_size: int
    total: int
    pages: int


class ImportHistoryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    mode: str
    status: str
    rows_read: int
    inserted_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None


class ImportResult(BaseModel):
    dataset: DatasetPublic
    history: ImportHistoryPublic


class SyncStatus(BaseModel):
    configured: bool
    latest_import: ImportHistoryPublic | None
