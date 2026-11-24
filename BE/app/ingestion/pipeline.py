from app.ingestion.reader import parse_csv_bytes


def normalize_csv(content: bytes) -> dict:
    rows = parse_csv_bytes(content)
    months = [row["month"] for row in rows]
    return {
        "rows": rows,
        "rows_read": len(rows),
        "start_month": min(months),
        "end_month": max(months),
    }
