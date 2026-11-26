"""One-shot backfill for the missing 2026-11-25 NEM daily demand observation."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Dataset
from app.nem.client import NEMClientError, OpenElectricityClient
from app.nem.schemas import NEMObservationRecord
from app.services.nem_import import (
    NEM_DATASET_NAME,
    NEM_DATASET_SOURCE,
    import_nem_observations,
)

TARGET_DATE = date(2026, 11, 25)
EXPECTED_DATASET_ID = 4
BRISBANE = ZoneInfo("Australia/Brisbane")
LOGGER = logging.getLogger("app.nem.daily_backfill")


class NEMDailyBackfillError(RuntimeError):
    """The requested backfill cannot safely be completed."""


def target_date_range(target_date: date = TARGET_DATE) -> tuple[datetime, datetime]:
    """Return the one-local-day half-open interval in NEM network time."""
    start = datetime.combine(target_date, time.min, tzinfo=BRISBANE)
    end = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=BRISBANE)
    return start, end


def run_daily_demand_backfill(
    *,
    client: OpenElectricityClient,
    session_factory: Callable[[], Session],
    importer: Callable | None = None,
    target_date: date = TARGET_DATE,
):
    """Fetch and persist only network-level daily demand for ``target_date``.

    The Dataset identity is checked before making the API request. No import
    history is created unless the API response contains a valid target-day row.
    """
    start, end = target_date_range(target_date)
    with session_factory() as db:
        dataset = db.scalar(
            select(Dataset).where(
                Dataset.id == EXPECTED_DATASET_ID,
                Dataset.name == NEM_DATASET_NAME,
                Dataset.source == NEM_DATASET_SOURCE,
            )
        )
    if dataset is None:
        raise NEMDailyBackfillError(
            "Expected Open Electricity NEM Dataset ID 4 was not found; no API request or import was made"
        )

    try:
        records = client.get_observations(
            "NEM", ("demand",), "1d", start, end, "network"
        )
    except NEMClientError as exc:
        raise NEMDailyBackfillError(
            f"Open Electricity daily demand request or response validation failed: {exc}"
        ) from None

    target_records = _validate_target_records(records, target_date, start)
    persist = importer or import_nem_observations
    with session_factory() as db:
        return persist(db, target_records)


def _validate_target_records(
    records: Sequence[NEMObservationRecord],
    target_date: date,
    start: datetime,
) -> list[NEMObservationRecord]:
    if records is None or not records:
        raise NEMDailyBackfillError(
            f"Open Electricity returned no observations for NEM daily demand on {target_date.isoformat()}; nothing was imported"
        )

    target_records: list[NEMObservationRecord] = []
    natural_keys: set[tuple[object, ...]] = set()
    expected_instant = start.astimezone(timezone.utc)
    for record in records:
        if record is None:
            raise NEMDailyBackfillError(
                "API response contains a null observation; nothing was imported"
            )
        observed_at = record.observed_at
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise NEMDailyBackfillError("API returned a timezone-naive observation; nothing was imported")
        if (
            record.network_code != "NEM"
            or record.metric != "demand"
            or record.interval != "1d"
            or record.unit != "MW"
            or record.grouping_type != "network"
            or record.grouping_code != ""
        ):
            raise NEMDailyBackfillError(
                "API response does not match the required NEM daily network demand MW contract; nothing was imported"
            )
        observed_instant = observed_at.astimezone(timezone.utc)
        if observed_instant != expected_instant:
            raise NEMDailyBackfillError(
                f"API response observation does not match the required instant for Brisbane date {target_date.isoformat()}; nothing was imported"
            )

        natural_key = (
            record.network_code,
            record.metric,
            record.interval,
            observed_instant,
            record.result,
            record.grouping_type,
            record.grouping_code,
        )
        if natural_key in natural_keys:
            raise NEMDailyBackfillError(
                "API response contains duplicate observation natural keys; nothing was imported"
            )
        natural_keys.add(natural_key)
        target_records.append(record)

    if not target_records:
        raise NEMDailyBackfillError(
            f"API response contains no NEM daily demand observation for Brisbane date {target_date.isoformat()}; nothing was imported"
        )
    return target_records


def main(
    *,
    client: OpenElectricityClient | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> int:
    """CLI entrypoint. Dependencies are injectable for isolated unit tests."""
    logging.basicConfig(level="INFO")
    try:
        if client is None:
            client = OpenElectricityClient()
        if session_factory is None:
            from app.db.database import get_session_factory

            session_factory = get_session_factory()
        history = run_daily_demand_backfill(
            client=client,
            session_factory=session_factory,
        )
    except (NEMDailyBackfillError, NEMClientError) as exc:
        LOGGER.error("NEM daily backfill failed: %s", exc)
        return 2
    except Exception as exc:
        # Do not log exception text from unexpected DB/configuration errors;
        # it may contain a URL or other operational details.
        LOGGER.error("NEM daily backfill failed (%s)", type(exc).__name__)
        return 2

    LOGGER.info(
        "NEM daily backfill completed: import_id=%s dataset_id=%s rows=%s inserted=%s updated=%s skipped=%s",
        history.id,
        history.dataset_id,
        history.rows_read,
        history.inserted_count,
        history.updated_count,
        history.skipped_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
