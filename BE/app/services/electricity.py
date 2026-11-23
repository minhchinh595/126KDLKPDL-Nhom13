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
