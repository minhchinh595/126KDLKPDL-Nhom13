from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_analyst
from app.db.database import get_db
from app.db.models import Dataset, ElectricityConsumption, ModelRun
from app.schemas.dashboard import DashboardOverview

router = APIRouter(prefix="/dashboard", dependencies=[Depends(require_analyst)])


@router.get("/overview", response_model=DashboardOverview)
def dashboard_overview(db: Session = Depends(get_db)):
    base = select(ElectricityConsumption).where(
        ElectricityConsumption.iso3 == "VNM", ElectricityConsumption.metric == "demand",
        ElectricityConsumption.fuel.is_(None), ElectricityConsumption.unit == "TWh",
    ).subquery()
    aggregate = db.execute(select(
        func.count(base.c.id), func.min(base.c.month), func.max(base.c.month),
        func.avg(base.c.value), func.min(base.c.value), func.max(base.c.value),
    )).one()
    latest = db.execute(select(base.c.month, base.c.value).order_by(base.c.month.desc()).limit(1)).first()
    previous = None
    if latest:
        previous_month = (latest.month - timedelta(days=1)).replace(day=1)
        previous = db.scalar(select(base.c.value).where(base.c.month == previous_month))
    dataset_count = db.scalar(select(func.count()).select_from(Dataset)) or 0
    model_run_count = db.scalar(select(func.count()).select_from(ModelRun)) or 0
    latest_dataset_update = db.scalar(select(func.max(Dataset.updated_at)))
    change_pct = round((float(latest.value) - float(previous)) / float(previous) * 100, 4) if latest and previous not in (None, 0) else None
    return {
        "record_count": aggregate[0],
        "start_month": aggregate[1].strftime("%Y-%m") if aggregate[1] else None,
        "latest_month": latest.month.strftime("%Y-%m") if latest else None,
        "mean_demand_twh": round(float(aggregate[3]), 4) if aggregate[3] is not None else None,
        "minimum_demand_twh": round(float(aggregate[4]), 4) if aggregate[4] is not None else None,
        "maximum_demand_twh": round(float(aggregate[5]), 4) if aggregate[5] is not None else None,
        "latest_demand_twh": float(latest.value) if latest else None,
        "change_from_previous_month_pct": change_pct,
        "dataset_count": dataset_count,
        "model_run_count": model_run_count,
        "data_updated_at": latest_dataset_update,
        "unit": "TWh",
    }
