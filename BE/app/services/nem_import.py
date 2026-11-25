"""Persist parsed Open Electricity NEM observations and import history."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from sqlalchemy import Boolean, func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Dataset, DatasetImport, NEMObservation
from app.nem.schemas import NEMObservationRecord, SUPPORTED_METRICS_BY_INTERVAL


NEM_DATASET_NAME = "Open Electricity NEM"
NEM_DATASET_SOURCE = "https://api.openelectricity.org.au/v4/market/network/NEM"
NEM_DATASET_FILE_NAME = "Open Electricity API observations"
NEM_DATASET_DESCRIPTION = "NEM market observations retrieved from the Open Electricity API."


class NEMImportError(ValueError):
    """Raised when a parsed observation batch is invalid for persistence."""


class NEMImportHistoryError(RuntimeError):
    """Raised when an import failure cannot be persisted to import history."""


def import_nem_observations(
    db: Session,
    observations: Sequence[NEMObservationRecord | Mapping[str, Any]],
) -> DatasetImport:
    """Upsert one NEM interval batch and persist its import history.

    Dataset creation and the running history row are committed first. The
    observation upsert and successful metadata/history updates share a second
    transaction so a failed batch cannot leave partial observations behind.
    """
    records = _normalize_records(observations)
    interval = records[0]["interval"]
    mode = {"5m": "nem_api_5m", "1d": "nem_api_daily"}[interval]

    try:
        with db.begin():
            dataset = _get_or_create_dataset(db)
            history = DatasetImport(
                dataset_id=dataset.id,
                mode=mode,
                status="running",
                rows_read=len(records),
                inserted_count=0,
                updated_count=0,
                skipped_count=0,
                error_count=0,
            )
            db.add(history)
            db.flush()
            dataset_id = dataset.id
            history_id = history.id
    except Exception:
        db.rollback()
        raise

    try:
        _reject_duplicate_batch_keys(records)
        with db.begin():
            inserted_count, updated_count, skipped_count = _upsert_records(
                db, dataset_id, records
            )
            _refresh_dataset_metadata(db, dataset_id, records)

            history = db.get(DatasetImport, history_id)
            if history is None:
                raise RuntimeError("NEM import history row disappeared")
            history.status = "completed"
            history.rows_read = len(records)
            history.inserted_count = inserted_count
            history.updated_count = updated_count
            history.skipped_count = skipped_count
            history.error_count = 0
            history.error_message = None
            history.completed_at = datetime.now(timezone.utc)

        completed = db.get(DatasetImport, history_id)
        if completed is None:
            raise RuntimeError("NEM import history row disappeared after commit")
        return completed
    except Exception as exc:
        db.rollback()
        try:
            _persist_failed_history(db, dataset_id, history_id, len(records), exc)
        except Exception as history_exc:
            db.rollback()
            raise NEMImportHistoryError(
                "NEM import failed and its failure history could not be saved"
            ) from history_exc
        raise


def _get_or_create_dataset(db: Session) -> Dataset:
    matches = db.scalars(
        select(Dataset).where(
            Dataset.name == NEM_DATASET_NAME,
            Dataset.source == NEM_DATASET_SOURCE,
        )
    ).all()
    if len(matches) > 1:
        raise NEMImportError("multiple Dataset rows match the NEM name and source")
    if matches:
        dataset = matches[0]
        dataset.file_name = NEM_DATASET_FILE_NAME
        dataset.description = NEM_DATASET_DESCRIPTION
        return dataset

    conflicting_dataset = db.scalar(
        select(Dataset.id).where(Dataset.name == NEM_DATASET_NAME).limit(1)
    )
    if conflicting_dataset is not None:
        raise NEMImportError(
            "Dataset name 'Open Electricity NEM' is already used by a different source"
        )

    dataset = Dataset(
        name=NEM_DATASET_NAME,
        source=NEM_DATASET_SOURCE,
        file_name=NEM_DATASET_FILE_NAME,
        description=NEM_DATASET_DESCRIPTION,
        record_count=0,
        status="importing",
    )
    db.add(dataset)
    db.flush()
    return dataset


def _normalize_records(
    observations: Sequence[NEMObservationRecord | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(observations, (str, bytes)) or not observations:
        raise NEMImportError("observation batch must be non-empty")

    records: list[dict[str, Any]] = []
    intervals: set[str] = set()
    for observation in observations:
        if isinstance(observation, NEMObservationRecord):
            raw = observation.as_dict()
        elif isinstance(observation, Mapping):
            raw = observation
        else:
            raise NEMImportError("observation batch contains an unsupported record")

        fields = (
            "network_code",
            "metric",
            "interval",
            "observed_at",
            "value",
            "unit",
            "result",
            "grouping_type",
            "grouping_code",
        )
        if any(field not in raw for field in fields):
            raise NEMImportError("observation batch contains an incomplete record")

        network_code = raw["network_code"]
        metric = raw["metric"]
        interval = raw["interval"]
        unit = raw["unit"]
        result = raw["result"]
        grouping_type = raw["grouping_type"]
        grouping_code = raw["grouping_code"]
        observed_at = raw["observed_at"]

        if network_code != "NEM":
            raise NEMImportError("only NEM network observations can be imported")
        if (
            not isinstance(metric, str)
            or not isinstance(interval, str)
            or metric not in SUPPORTED_METRICS_BY_INTERVAL.get(interval, ())
        ):
            raise NEMImportError("observation metric and interval are unsupported")
        if not isinstance(metric, str) or not isinstance(unit, str) or not unit.strip():
            raise NEMImportError("observation metric and unit are required")
        if not isinstance(result, str) or not result.strip():
            raise NEMImportError("observation result is required")
        if not isinstance(grouping_type, str) or grouping_type not in {"network", "network_region"}:
            raise NEMImportError("observation grouping type is unsupported")
        if not isinstance(grouping_code, str):
            raise NEMImportError("observation grouping code must be a string")
        if (grouping_type == "network" and grouping_code) or (
            grouping_type == "network_region" and not grouping_code.strip()
        ):
            raise NEMImportError("observation grouping code does not match grouping type")
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise NEMImportError("observation timestamp must be timezone-aware")
        if isinstance(raw["value"], bool):
            raise NEMImportError("observation value must be a finite number")
        try:
            value = raw["value"] if isinstance(raw["value"], Decimal) else Decimal(str(raw["value"]))
        except (InvalidOperation, TypeError, ValueError):
            raise NEMImportError("observation value must be a finite number") from None
        if not value.is_finite():
            raise NEMImportError("observation value must be a finite number")

        intervals.add(interval)
        records.append(
            {
                "network_code": network_code,
                "metric": metric,
                "interval": interval,
                "observed_at": observed_at,
                "value": value,
                "unit": unit,
                "result": result,
                "grouping_type": grouping_type,
                "grouping_code": grouping_code,
            }
        )

    if len(intervals) != 1:
        raise NEMImportError("one import batch must contain exactly one interval")
    return records


def _natural_key(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        record["network_code"],
        record["metric"],
        record["interval"],
        record["observed_at"].astimezone(timezone.utc),
        record["result"],
        record["grouping_type"],
        record["grouping_code"],
    )


def _reject_duplicate_batch_keys(records: Sequence[Mapping[str, Any]]) -> None:
    seen: set[tuple[Any, ...]] = set()
    for record in records:
        key = _natural_key(record)
        if key in seen:
            raise NEMImportError("observation batch contains duplicate natural keys")
        seen.add(key)


def _upsert_records(
    db: Session,
    dataset_id: int,
    records: Sequence[Mapping[str, Any]],
) -> tuple[int, int, int]:
    statement = insert(NEMObservation).values(
        [{**record, "dataset_id": dataset_id} for record in records]
    )
    excluded = statement.excluded
    statement = statement.on_conflict_do_update(
        constraint="uq_nem_observations_natural_key",
        set_={
            "dataset_id": excluded.dataset_id,
            "value": excluded.value,
            "unit": excluded.unit,
        },
        where=or_(
            NEMObservation.dataset_id.is_distinct_from(excluded.dataset_id),
            NEMObservation.value.is_distinct_from(excluded.value),
            NEMObservation.unit.is_distinct_from(excluded.unit),
        ),
    ).returning(literal_column("xmax = 0", type_=Boolean).label("was_inserted"))

    returned = db.execute(statement).scalars().all()
    inserted_count = sum(bool(was_inserted) for was_inserted in returned)
    updated_count = len(returned) - inserted_count
    skipped_count = len(records) - len(returned)
    return inserted_count, updated_count, skipped_count


def _refresh_dataset_metadata(
    db: Session,
    dataset_id: int,
    records: Sequence[Mapping[str, Any]],
) -> None:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise RuntimeError("NEM Dataset row disappeared")

    record_count = db.scalar(
        select(func.count())
        .select_from(NEMObservation)
        .where(NEMObservation.dataset_id == dataset_id)
    ) or 0
    if not record_count:
        raise RuntimeError("NEM observation import produced no persisted records")

    batch_start = min(record["observed_at"].date() for record in records)
    batch_end = max(record["observed_at"].date() for record in records)
    if dataset.record_count == 0 or dataset.start_date is None:
        dataset.start_date = batch_start
    else:
        dataset.start_date = min(dataset.start_date, batch_start)
    if dataset.record_count == 0 or dataset.end_date is None:
        dataset.end_date = batch_end
    else:
        dataset.end_date = max(dataset.end_date, batch_end)

    dataset.record_count = record_count
    dataset.status = "ready"


def _persist_failed_history(
    db: Session,
    dataset_id: int,
    history_id: int,
    rows_read: int,
    error: Exception,
) -> None:
    with db.begin():
        history = db.get(DatasetImport, history_id)
        if history is None:
            raise RuntimeError("NEM import history row disappeared")
        history.status = "failed"
        history.rows_read = rows_read
        history.inserted_count = 0
        history.updated_count = 0
        history.skipped_count = 0
        history.error_count = 1
        history.error_message = _safe_error_message(error)
        history.completed_at = datetime.now(timezone.utc)

        dataset = db.get(Dataset, dataset_id)
        if dataset is not None and dataset.status == "importing":
            existing_count = db.scalar(
                select(func.count())
                .select_from(NEMObservation)
                .where(NEMObservation.dataset_id == dataset_id)
            ) or 0
            if existing_count == 0:
                dataset.status = "failed"


def _safe_error_message(error: Exception) -> str:
    if isinstance(error, NEMImportError):
        return str(error)[:2000]
    # Database/driver exception strings can contain URLs, SQL parameters, or
    # credentials. Persist only the exception class for those failures.
    return f"NEM import failed ({type(error).__name__})"
