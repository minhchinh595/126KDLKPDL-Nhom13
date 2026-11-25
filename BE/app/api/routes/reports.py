import csv
import io
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import require_analyst
from app.api.routes.analysis import get_correlation, get_distribution, get_seasonality, get_summary, get_trend
from app.api.routes.dashboard import dashboard_overview
from app.db.database import get_db
from app.db.models import ModelRun
from app.schemas.reports import ReportAnalysis, ReportModelRuns, ReportSummary
from app.services.nem_data import NEMDatasetUnavailable, query_observations

router = APIRouter(prefix="/reports", dependencies=[Depends(require_analyst)])


@router.get("/summary", response_model=ReportSummary)
def report_summary(db: Session = Depends(get_db)):
    return {"generated_at": datetime.now().astimezone(), "dashboard": dashboard_overview(db)}


@router.get("/analysis", response_model=ReportAnalysis)
def report_analysis(start_at: datetime | None = None, end_at: datetime | None = None, db: Session = Depends(get_db)):
    return {
        "dataset_name": "Open Electricity NEM", "timezone": "Australia/Brisbane",
        "start_at": start_at, "end_at": end_at,
        "summary": get_summary(start_at, end_at, db),
        "trend": get_trend(start_at=start_at, end_at=end_at, view="month", db=db),
        "seasonality": get_seasonality(start_at, end_at, db),
        "correlation": get_correlation(start_at, end_at, db),
        "distribution": get_distribution("demand", "1d", start_at, end_at, 10, db),
    }


@router.get("/model-runs", response_model=ReportModelRuns)
def report_model_runs(model_type: Literal["clustering", "prediction", "classification"] | None = None, db: Session = Depends(get_db)):
    statement = select(ModelRun).order_by(ModelRun.created_at.desc(), ModelRun.id.desc())
    if model_type:
        statement = statement.where(ModelRun.model_type == model_type)
    runs = db.scalars(statement.limit(500)).all()
    return {"items": runs, "limit": 500}


@router.get("/export")
def export_report(report_type: Literal["demand", "model-runs"] = "demand", metric: str = "demand", interval: str = "1d", start_at: datetime | None = None, end_at: datetime | None = None, page: int = Query(1, ge=1), page_size: int = Query(1000, ge=1, le=1000), db: Session = Depends(get_db)):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    try:
        if report_type == "demand":
            _, rows, _ = query_observations(db, metric=metric, interval=interval, start_at=start_at, end_at=end_at, page=page, page_size=page_size)
            writer.writerow(["network_code", "metric", "interval", "unit", "observed_at", "value", "result", "grouping_type", "grouping_code"])
            for row in rows:
                writer.writerow([row.network_code, row.metric, row.interval, row.unit, row.observed_at.isoformat(), row.value, row.result, row.grouping_type, row.grouping_code])
            filename = "nem_observations_report.csv"
        else:
            writer.writerow(["id", "model_type", "status", "created_at", "started_at", "completed_at", "parameters", "metrics", "error_message"])
            for row in db.scalars(select(ModelRun).order_by(ModelRun.created_at.desc()).limit(500)):
                writer.writerow([row.id, row.model_type, row.status, row.created_at, row.started_at, row.completed_at, row.parameters, row.metrics, row.error_message])
            filename = "model_runs_report.csv"
    except NEMDatasetUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Report data is unavailable") from exc
    return Response(stream.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename={filename}"})
