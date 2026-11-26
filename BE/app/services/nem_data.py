"""Read-only access to the active Open Electricity NEM dataset."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Dataset, NEMObservation
from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE
from app.nem.schemas import SUPPORTED_METRICS_BY_INTERVAL

NEM_TIMEZONE = "Australia/Brisbane"
MAX_PAGE_SIZE = 1000
MAX_FIVE_MINUTE_RANGE = timedelta(days=7)
BRISBANE = ZoneInfo(NEM_TIMEZONE)


class NEMDatasetUnavailable(RuntimeError):
    """The configured NEM dataset is missing or ambiguous."""


def resolve_nem_dataset(db: Session) -> Dataset:
    matches = db.scalars(select(Dataset).where(
        Dataset.name == NEM_DATASET_NAME, Dataset.source == NEM_DATASET_SOURCE
    )).all()
    if not matches:
        raise NEMDatasetUnavailable("Open Electricity NEM dataset is not available")
    if len(matches) != 1:
        raise NEMDatasetUnavailable("Open Electricity NEM dataset is ambiguous")
    return matches[0]


def query_observations(
    db: Session,
    *,
    metric: str,
    interval: str,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    network_code: str = "NEM",
    grouping_type: str = "network",
    grouping_code: str = "",
    page: int = 1,
    page_size: int = 500,
) -> tuple[Dataset, list[NEMObservation], int]:
    if page < 1 or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError(f"page must be positive and page_size must be 1..{MAX_PAGE_SIZE}")
    if metric not in SUPPORTED_METRICS_BY_INTERVAL.get(interval, ()):
        raise ValueError("metric and interval combination is unsupported")
    if network_code != "NEM" or grouping_type != "network" or grouping_code != "":
        raise ValueError("only network-level NEM observations are supported")
    for name, value in (("start_at", start_at), ("end_at", end_at)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError(f"{name} must be timezone-aware")
    if start_at and end_at and start_at.astimezone(timezone.utc) >= end_at.astimezone(timezone.utc):
        raise ValueError("start_at must be earlier than end_at")
    if interval == "5m":
        if start_at is None or end_at is None:
            raise ValueError("5m queries require start_at and end_at")
        if end_at.astimezone(timezone.utc) - start_at.astimezone(timezone.utc) > MAX_FIVE_MINUTE_RANGE:
            raise ValueError("5m query range cannot exceed 7 days")
    dataset = resolve_nem_dataset(db)
    filters = [
        NEMObservation.dataset_id == dataset.id,
        NEMObservation.network_code == network_code,
        NEMObservation.metric == metric,
        NEMObservation.interval == interval,
        NEMObservation.grouping_type == grouping_type,
        NEMObservation.grouping_code == grouping_code,
    ]
    if start_at is not None:
        filters.append(NEMObservation.observed_at >= start_at)
    if end_at is not None:
        filters.append(NEMObservation.observed_at < end_at)
    count = db.query(NEMObservation).filter(*filters).count()
    rows = db.scalars(select(NEMObservation).where(*filters).order_by(
        NEMObservation.observed_at, NEMObservation.result, NEMObservation.id
    ).offset((page - 1) * page_size).limit(page_size)).all()
    return dataset, rows, count


def coverage(rows: list[NEMObservation], interval: str, start_at: datetime | None, end_at: datetime | None) -> dict:
    result = {
        "returned_count": len(rows),
        "first_observed_at": rows[0].observed_at.isoformat() if rows else None,
        "last_observed_at": rows[-1].observed_at.isoformat() if rows else None,
        "missing_timestamps": [],
        "note": "No missing values are synthesized.",
    }
    if interval != "5m" or start_at is None or end_at is None:
        return result
    expected = int((end_at - start_at).total_seconds() // 300)
    if expected > 2016:
        result["note"] = "Missing timestamp enumeration is limited to ranges of at most 7 days."
        return result
    present = {row.observed_at for row in rows}
    missing = []
    cursor = start_at
    while cursor < end_at:
        if cursor not in present:
            missing.append(cursor.isoformat())
        cursor += timedelta(minutes=5)
    result["expected_count"] = expected
    result["missing_count"] = len(missing)
    result["missing_timestamps"] = missing
    return result


def query_coverage(db: Session, metric: str, interval: str, start_at: datetime | None, end_at: datetime | None) -> dict:
    dataset = resolve_nem_dataset(db)
    filters = [
        NEMObservation.dataset_id == dataset.id,
        NEMObservation.network_code == "NEM",
        NEMObservation.metric == metric,
        NEMObservation.interval == interval,
        NEMObservation.grouping_type == "network",
        NEMObservation.grouping_code == "",
    ]
    if start_at is not None: filters.append(NEMObservation.observed_at >= start_at)
    if end_at is not None: filters.append(NEMObservation.observed_at < end_at)
    timestamps = db.scalars(select(NEMObservation.observed_at).where(*filters).order_by(NEMObservation.observed_at)).all()
    if interval == "5m":
        if start_at is None or end_at is None:
            raise ValueError("5m queries require start_at and end_at")
        start_utc = start_at.astimezone(timezone.utc)
        end_utc = end_at.astimezone(timezone.utc)
        if end_utc - start_utc > MAX_FIVE_MINUTE_RANGE:
            raise ValueError("5m query range cannot exceed 7 days")
        observed = {value.astimezone(timezone.utc) for value in timestamps}
        cursor = datetime.fromtimestamp(((start_utc.timestamp() + 299) // 300) * 300, timezone.utc)
        expected = max(0, int((end_utc - cursor).total_seconds() // 300) + (1 if (end_utc - cursor).total_seconds() % 300 else 0))
        missing = []
        while cursor < end_utc:
            if cursor not in observed:
                missing.append(cursor.astimezone(BRISBANE).isoformat())
            cursor += timedelta(minutes=5)
        return {"expected_count": expected, "observed_count": len(observed), "missing_count": len(missing), "missing_timestamps": missing, "note": "No missing values are synthesized."}

    observed_dates = {value.astimezone(BRISBANE).date() for value in timestamps}
    if not observed_dates:
        return {"expected_count": 0, "observed_count": 0, "missing_count": 0, "missing_timestamps": [], "note": "No observations in the requested range."}
    first = start_at.astimezone(BRISBANE).date() if start_at else min(observed_dates)
    if end_at:
        local_end = end_at.astimezone(BRISBANE)
        last_exclusive = local_end.date() + (timedelta(days=1) if local_end.time().replace(tzinfo=None) > datetime.min.time() else timedelta())
    else:
        last_exclusive = max(observed_dates) + timedelta(days=1)
    expected = max(0, (last_exclusive - first).days)
    if expected > 3660:
        return {"expected_count": None, "observed_count": len(observed_dates), "missing_count": None, "missing_timestamps": [], "note": "Gap enumeration is limited to 10 years."}
    missing = [(first + timedelta(days=offset)).isoformat() for offset in range(expected) if first + timedelta(days=offset) not in observed_dates]
    return {"expected_count": expected, "observed_count": len(observed_dates), "missing_count": len(missing), "missing_timestamps": missing, "note": "Daily timestamps are NEM-local dates; no missing values are synthesized."}
