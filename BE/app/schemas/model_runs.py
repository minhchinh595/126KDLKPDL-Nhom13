from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ModelRunPublic(BaseModel):
    id: int
    model_type: Literal["clustering", "prediction", "classification"]
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    parameters: dict[str, Any] | None
    metrics: dict[str, Any] | None
    error_message: str | None


class ModelRunListResponse(BaseModel):
    items: list[ModelRunPublic]
    page: int
    page_size: int
    total: int
    pages: int
