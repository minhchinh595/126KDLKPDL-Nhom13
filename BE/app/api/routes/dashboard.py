from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import require_analyst
from app.db.database import get_db
from app.schemas.dashboard import DashboardOverview
from app.services.nem_data import NEMDatasetUnavailable, query_observations, resolve_nem_dataset

router = APIRouter(prefix="/dashboard", dependencies=[Depends(require_analyst)])


def dashboard_overview(db: Session = Depends(get_db)):
    try:
        dataset = resolve_nem_dataset(db)
        def values(metric):
            _, rows, _ = query_observations(db, metric=metric, interval="1d", page=1, page_size=1000)
            return rows
        demand = values("demand")
        renewable = values("renewable_proportion")
        prices = values("price")
        vals = [float(row.value) for row in demand]
        return {
            "dataset_name": dataset.name, "dataset_status": dataset.status,
            "total_observations": dataset.record_count,
            "latest_daily_demand_mw": float(demand[-1].value) if demand else None,
            "average_daily_demand_mw": sum(vals) / len(vals) if vals else None,
            "minimum_daily_demand_mw": min(vals) if vals else None,
            "maximum_daily_demand_mw": max(vals) if vals else None,
            "latest_renewable_proportion_percent": float(renewable[-1].value) if renewable else None,
            "latest_price_per_mwh": float(prices[-1].value) if prices else None,
            "latest_data_timestamp": max((row.observed_at for row in [*demand, *renewable, *prices]), default=None),
            "timezone": "Australia/Brisbane",
        }
    except NEMDatasetUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="NEM observations are unavailable") from exc


@router.get("/overview", response_model=DashboardOverview)
def get_dashboard_overview(db: Session = Depends(get_db)):
    return dashboard_overview(db)
