from decimal import Decimal, InvalidOperation

from app.ingestion.date_utils import parse_month


def clean_row(raw: dict[str | None, str | None], line_number: int) -> dict:
    """Validate and normalize one monthly VNM demand CSV row."""
    if None in raw:
        raise ValueError("row contains more values than the CSV header")
    required_columns = {
        "country_id", "country", "iso3", "month", "metric", "fuel", "value", "unit"
    }
    if any(not (raw.get(column) or "").strip() for column in required_columns - {"fuel"}):
        raise ValueError("required value is blank")

    try:
        month = parse_month((raw.get("month") or "").strip())
        value = Decimal((raw.get("value") or "").strip())
    except (ValueError, InvalidOperation) as exc:
        raise ValueError(str(exc)) from exc
    if not value.is_finite() or value < 0:
        raise ValueError("value must be a finite non-negative number")

    row = {
        "country_id": (raw.get("country_id") or "").strip(),
        "country": (raw.get("country") or "").strip(),
        "iso3": (raw.get("iso3") or "").strip().upper(),
        "month": month,
        "metric": (raw.get("metric") or "").strip(),
        "fuel": (raw.get("fuel") or "").strip() or None,
        "value": value,
        "unit": (raw.get("unit") or "").strip(),
    }
    if len(row["iso3"]) != 3:
        raise ValueError("iso3 must contain exactly three characters")
    if (
        row["iso3"] != "VNM"
        or row["metric"] != "demand"
        or row["fuel"] is not None
        or row["unit"] != "TWh"
    ):
        raise ValueError("only VNM monthly demand with blank fuel and TWh units is supported")
    if len(value.as_tuple().digits) > 14 or max(-value.as_tuple().exponent, 0) > 4:
        raise ValueError("value exceeds the supported NUMERIC(14, 4) precision")
    return row
