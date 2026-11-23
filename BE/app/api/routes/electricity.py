from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.services.electricity import load_demand

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
def get_demand(response: Response):
    """Return all available months so frontend filters retain comparison history."""
    response.headers["Cache-Control"] = "no-store"
    try:
        return load_demand()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=503, detail="Demand dataset is unavailable or invalid") from exc
