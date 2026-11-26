from datetime import date, datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE


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

    @computed_field
    @property
    def source_role(self) -> Literal["active_nem", "legacy"]:
        """Identify retained VNM datasets without changing their stored metadata."""
        if self.name == NEM_DATASET_NAME and self.source == NEM_DATASET_SOURCE:
            return "active_nem"
        return "legacy"


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
