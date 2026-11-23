from math import ceil
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_analyst
from app.db.database import get_db
from app.db.models import ModelRun
from app.schemas.model_runs import ModelRunListResponse, ModelRunPublic

router = APIRouter(prefix="/model-runs", dependencies=[Depends(require_analyst)])


@router.get("", response_model=ModelRunListResponse)
def list_model_runs(
    model_type: Literal["clustering", "prediction", "classification"] | None = None,
    run_status: Literal["queued", "running", "completed", "failed"] | None = Query(None, alias="status"),
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    statement, count_statement = select(ModelRun), select(func.count()).select_from(ModelRun)
    if model_type:
        statement, count_statement = statement.where(ModelRun.model_type == model_type), count_statement.where(ModelRun.model_type == model_type)
    if run_status:
        statement, count_statement = statement.where(ModelRun.status == run_status), count_statement.where(ModelRun.status == run_status)
    total = db.scalar(count_statement) or 0
    sort_column = ModelRun.created_at.asc() if order == "asc" else ModelRun.created_at.desc()
    sort_id = ModelRun.id.asc() if order == "asc" else ModelRun.id.desc()
    items = db.scalars(statement.order_by(sort_column, sort_id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": items, "page": page, "page_size": page_size, "total": total, "pages": ceil(total / page_size)}


@router.get("/{run_id}", response_model=ModelRunPublic)
def get_model_run(run_id: int, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    run = db.get(ModelRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Model run not found")
    return run
