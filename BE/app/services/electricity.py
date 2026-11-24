"""Read the project's processed demand dataset without hardcoded chart values."""

import csv
import math
import os
import re
from pathlib import Path

DEFAULT_DATA_PATH = Path(__file__).resolve().parents[3] / "data" / "processed" / "vietnam_electricity_demand.csv"


def load_demand(path: Path | None = None) -> dict:
    data_path = path or Path(os.environ.get("ELECTRICITY_DATA_PATH", str(DEFAULT_DATA_PATH)))
    records = []
    months = set()
    with data_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"iso3", "month", "metric", "fuel", "value", "unit"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Dataset columns are invalid")
        for row in reader:
            if any(row.get(column) is None for column in required):
                raise ValueError("Dataset contains incomplete records")
            if row["iso3"] != "VNM" or row["metric"] != "demand" or row["fuel"].strip():
                continue
            month = row["month"].strip()
            value = float(row["value"])
            if (not re.fullmatch(r"[1-9]\d{3}-(0[1-9]|1[0-2])", month)
                    or not math.isfinite(value) or value < 0 or row["unit"] != "TWh"
                    or month in months):
                raise ValueError("Dataset contains invalid or duplicate demand records")
            months.add(month)
            records.append({"month": month, "value": value})
    records.sort(key=lambda row: row["month"])
    return {
        "source": "data/processed/vietnam_electricity_demand.csv" if data_path.resolve() == DEFAULT_DATA_PATH.resolve() else data_path.name,
        "country": "Vietnam",
        "iso3": "VNM",
        "unit": "TWh",
        "total": len(records),
        "start_month": records[0]["month"] if records else None,
        "end_month": records[-1]["month"] if records else None,
        "records": records,
    }

from datetime import date
import re

from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import ElectricityConsumption


def load_demand_from_db(
    session: Session,
    start_month: str | None = None,
    end_month: str | None = None,
    page: int = 1,
    page_size: int = 100,
) -> dict:
    """Read Vietnam's monthly electricity demand from PostgreSQL."""

    def parse_month(value: str | None, parameter_name: str) -> date | None:
        if value is None:
            return None

        if not re.fullmatch(r"[1-9]\d{3}-(0[1-9]|1[0-2])", value):
            raise ValueError(
                f"{parameter_name} must use YYYY-MM format"
            )

        return date.fromisoformat(f"{value}-01")

    start_date = parse_month(start_month, "start_month")
    end_date = parse_month(end_month, "end_month")

    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_month must be before or equal to end_month")

    statement = (
        select(
            ElectricityConsumption.id,
            ElectricityConsumption.month,
            ElectricityConsumption.value,
            ElectricityConsumption.country,
        )
        .where(
            ElectricityConsumption.iso3 == "VNM",
            ElectricityConsumption.metric == "demand",
            ElectricityConsumption.fuel.is_(None),
            ElectricityConsumption.unit == "TWh",
        )
        .order_by(ElectricityConsumption.month)
    )

    if start_date is not None:
        statement = statement.where(ElectricityConsumption.month >= start_date)

    if end_date is not None:
        statement = statement.where(ElectricityConsumption.month <= end_date)

    total_matches = session.scalar(select(func.count()).select_from(ElectricityConsumption).where(
        ElectricityConsumption.iso3 == "VNM",
        ElectricityConsumption.metric == "demand",
        ElectricityConsumption.fuel.is_(None),
        ElectricityConsumption.unit == "TWh",
        *([ElectricityConsumption.month >= start_date] if start_date is not None else []),
        *([ElectricityConsumption.month <= end_date] if end_date is not None else []),
    )) or 0
    if page_size > 0:
        statement = statement.offset((page - 1) * page_size).limit(page_size)
    rows = session.execute(statement).all()

    records = [
        {
            "id": row.id,
            "month": row.month.strftime("%Y-%m"),
            "value": float(row.value),
        }
        for row in rows
    ]

    return {
        "source": "PostgreSQL: electricity_consumption",
        "country": rows[0].country if rows else "Vietnam",
        "iso3": "VNM",
        "unit": "TWh",
        "total": len(records),
        "total_matches": total_matches,
        "page": page,
        "page_size": page_size,
        "start_month": records[0]["month"] if records else None,
        "end_month": records[-1]["month"] if records else None,
        "records": records,
    }
