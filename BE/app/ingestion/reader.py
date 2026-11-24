import csv
import io
from decimal import InvalidOperation

from app.ingestion.cleaner import clean_row
from app.ingestion.date_utils import parse_month


REQUIRED_COLUMNS = {
    "country_id", "country", "iso3", "month", "metric", "fuel", "value", "unit"
}


def parse_csv_bytes(content: bytes) -> list[dict]:
    """Parse and validate normalized monthly CSV bytes without filesystem or DB access."""
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    headers = reader.fieldnames or []
    if len(headers) != len(set(headers)) or any(not header.strip() for header in headers):
        raise ValueError("CSV headers must be present and unique")
    missing = REQUIRED_COLUMNS - set(headers)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    rows = []
    errors = []
    seen = set()
    for line_number, raw in enumerate(reader, start=2):
        try:
            row = clean_row(raw, line_number)
            key = (row["country_id"], row["month"], row["metric"], row["fuel"] or "")
            if key in seen:
                raise ValueError("duplicate natural key in CSV")
            seen.add(key)
            rows.append(row)
        except (ValueError, InvalidOperation) as exc:
            errors.append(f"line {line_number}: {exc}")

    if errors:
        raise ValueError("CSV validation failed:\n" + "\n".join(errors))
    if not rows:
        raise ValueError("CSV contains no data rows")
    return rows
