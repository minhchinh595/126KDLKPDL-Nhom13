from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_db

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    message: str
    project: str
    database: str


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    return {
        "status": "success",
        "message": "Backend API is running",
        "project": "Electricity Consumption Analytics",
        "database": "connected",
    }


@router.get("/health/ready", response_model=HealthResponse)
def readiness_check(db: Session = Depends(get_db)):
    return health_check(db)
