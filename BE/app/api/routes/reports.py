import csv
import io
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import require_analyst
from app.api.routes.analysis import get_correlation, get_distribution, get_seasonality, get_summary, get_trend
from app.api.routes.dashboard import dashboard_overview
from app.db.database import get_db
from app.db.models import ModelRun
from app.schemas.reports import ReportAnalysis, ReportModelRuns, ReportSummary

router = APIRouter(prefix="/reports", dependencies=[Depends(require_analyst)])


@router.get("/summary", response_model=ReportSummary)
def report_summary(db: Session = Depends(get_db)):
    return {"generated_at": datetime.now().astimezone(), "dashboard": dashboard_overview(db)}


@router.get("/analysis", response_model=ReportAnalysis)
def report_analysis(start_month: str | None = None, end_month: str | None = None, db: Session = Depends(get_db)):
    return {
        "unit": "TWh", "start_month": start_month, "end_month": end_month,
        "summary": get_summary(start_month, end_month, db),
        "trend": get_trend(start_month, end_month, 12, db),
        "seasonality": get_seasonality(start_month, end_month, db),
        "correlation": get_correlation(start_month, end_month, db),
        "distribution": get_distribution(start_month, end_month, 10, db),
    }


@router.get("/model-runs", response_model=ReportModelRuns)
def report_model_runs(model_type: Literal["clustering", "prediction", "classification"] | None = None, db: Session = Depends(get_db)):
    statement = select(ModelRun).order_by(ModelRun.created_at.desc(), ModelRun.id.desc())
    if model_type:
        statement = statement.where(ModelRun.model_type == model_type)
    runs = db.scalars(statement.limit(500)).all()
    return {"items": runs, "limit": 500}


@router.get("/export")
def export_report(report_type: Literal["demand", "model-runs"] = "demand", db: Session = Depends(get_db)):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    try:
        if report_type == "demand":
            from app.db.models import ElectricityConsumption
            rows = db.execute(select(ElectricityConsumption).where(
                ElectricityConsumption.iso3 == "VNM", ElectricityConsumption.metric == "demand",
                ElectricityConsumption.fuel.is_(None), ElectricityConsumption.unit == "TWh",
            ).order_by(ElectricityConsumption.month)).scalars()
            writer.writerow(["id", "country", "iso3", "month", "metric", "value", "unit"])
            for row in rows:
                writer.writerow([row.id, row.country, row.iso3, row.month.strftime("%Y-%m"), row.metric, row.value, row.unit])
            filename = "electricity_demand_report.csv"
        else:
            writer.writerow(["id", "model_type", "status", "created_at", "started_at", "completed_at", "parameters", "metrics", "error_message"])
            for row in db.scalars(select(ModelRun).order_by(ModelRun.created_at.desc()).limit(500)):
                writer.writerow([row.id, row.model_type, row.status, row.created_at, row.started_at, row.completed_at, row.parameters, row.metrics, row.error_message])
            filename = "model_runs_report.csv"
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Report data is unavailable") from exc
    return Response(stream.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename={filename}"})
