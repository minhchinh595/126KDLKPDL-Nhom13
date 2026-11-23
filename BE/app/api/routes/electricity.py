from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.electricity import load_demand_from_db

router = APIRouter()


class DemandRecord(BaseModel):
    month: str
    value: float = Field(ge=0, allow_inf_nan=False)


class DemandResponse(BaseModel):
    source: str
    country: str
    iso3: Literal["VNM"]
    unit: Literal["TWh"]
    total: int
    start_month: str | None
    end_month: str | None
    records: list[DemandRecord]


@router.get("/electricity/demand", response_model=DemandResponse)
def get_demand(
    response: Response,
    start_month: str | None = None,
    end_month: str | None = None,
    db: Session = Depends(get_db),
):
    """Return monthly Vietnam electricity demand stored in PostgreSQL."""
    response.headers["Cache-Control"] = "no-store"

    try:
        return load_demand_from_db(
            db,
            start_month=start_month,
            end_month=end_month,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Electricity data is unavailable in PostgreSQL",
        ) from exc