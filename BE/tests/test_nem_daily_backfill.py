from datetime import date, datetime
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.nem.client import NEMAPIError
from app.nem.schemas import NEMObservationRecord
from app.nem import daily_backfill
from app.nem.daily_backfill import (
    NEMDailyBackfillError,
    run_daily_demand_backfill,
    target_date_range,
)
from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE

BRISBANE = ZoneInfo("Australia/Brisbane")


def demand_record(observed_at="2026-11-25T00:00:00+10:00"):
    return NEMObservationRecord(
        network_code="NEM",
        metric="demand",
        interval="1d",
        observed_at=datetime.fromisoformat(observed_at),
        value=Decimal("18432.5"),
        unit="MW",
        result="demand_total",
        grouping_type="network",
        grouping_code="",
    )


class FakeClient:
    def __init__(self, records=(), error=None):
        self.records = None if records is None else list(records)
        self.error = error
        self.calls = []

    def get_observations(self, *args):
        self.calls.append(args)
        if self.error is not None:
            raise self.error
        return self.records


class FakeSession:
    def __init__(self, dataset=None):
        self.dataset = dataset or SimpleNamespace(
            id=4, name=NEM_DATASET_NAME, source=NEM_DATASET_SOURCE
        )

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def scalar(self, _statement):
        if (
            self.dataset.id != 4
            or self.dataset.name != NEM_DATASET_NAME
            or self.dataset.source != NEM_DATASET_SOURCE
        ):
            return None
        return self.dataset


def session_factory():
    return FakeSession()


def test_target_date_range_is_one_brisbane_calendar_day_half_open():
    start, end = target_date_range()

    assert start == datetime(2026, 11, 25, 0, 0, tzinfo=BRISBANE)
    assert end == datetime(2026, 11, 26, 0, 0, tzinfo=BRISBANE)
    assert start.astimezone(ZoneInfo("UTC")).isoformat() == "2026-11-24T14:00:00+00:00"
    assert end > start


@pytest.mark.parametrize(
    "timestamp",
    ["2026-11-24T14:00:00Z", "2026-11-25T00:00:00+10:00"],
)
def test_backfill_accepts_exact_target_instant_and_calls_daily_importer(timestamp):
    records = [demand_record(timestamp)]
    client = FakeClient(records)
    imported = SimpleNamespace(
        id=9, dataset_id=4, rows_read=1, inserted_count=1, updated_count=0, skipped_count=0
    )
    importer_calls = []

    def importer(db, batch):
        importer_calls.append((db, batch))
        return imported

    result = run_daily_demand_backfill(
        client=client, session_factory=session_factory, importer=importer
    )

    network, metrics, interval, start, end, grouping = client.calls[0]
    assert (network, metrics, interval, grouping) == ("NEM", ("demand",), "1d", "network")
    assert start == datetime(2026, 11, 25, 0, 0, tzinfo=BRISBANE)
    assert end == datetime(2026, 11, 26, 0, 0, tzinfo=BRISBANE)
    assert result is imported
    assert len(importer_calls) == 1
    assert importer_calls[0][1] == records


def test_empty_api_result_fails_without_creating_import_history():
    client = FakeClient()
    importer_calls = []

    with pytest.raises(NEMDailyBackfillError, match="returned no observations"):
        run_daily_demand_backfill(
            client=client,
            session_factory=session_factory,
            importer=lambda *_args: importer_calls.append(True),
        )

    assert client.calls
    assert importer_calls == []


def test_response_with_different_instant_on_target_day_is_rejected_before_import():
    client = FakeClient([demand_record("2026-11-25T01:00:00+10:00")])
    importer_calls = []

    with pytest.raises(NEMDailyBackfillError, match="does not match the required instant"):
        run_daily_demand_backfill(
            client=client,
            session_factory=session_factory,
            importer=lambda *_args: importer_calls.append(True),
        )

    assert importer_calls == []


def test_naive_timestamp_is_rejected_before_import():
    client = FakeClient([demand_record("2026-11-25T00:00:00")])
    importer_calls = []

    with pytest.raises(NEMDailyBackfillError, match="timezone-naive"):
        run_daily_demand_backfill(
            client=client,
            session_factory=session_factory,
            importer=lambda *_args: importer_calls.append(True),
        )

    assert importer_calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("network_code", "NSW1"),
        ("metric", "price"),
        ("interval", "5m"),
        ("unit", "MWh"),
        ("grouping_type", "network_region"),
        ("grouping_code", "NSW1"),
    ],
)
def test_contract_mismatch_is_rejected_before_import(field, value):
    client = FakeClient([replace(demand_record(), **{field: value})])
    importer_calls = []

    with pytest.raises(NEMDailyBackfillError, match="does not match the required"):
        run_daily_demand_backfill(
            client=client,
            session_factory=session_factory,
            importer=lambda *_args: importer_calls.append(True),
        )

    assert importer_calls == []


def test_duplicate_natural_key_is_rejected_before_import():
    record = demand_record("2026-11-24T14:00:00Z")
    same_instant_record = replace(
        record,
        observed_at=datetime.fromisoformat("2026-11-25T00:00:00+10:00"),
    )
    client = FakeClient([record, same_instant_record])
    importer_calls = []

    with pytest.raises(NEMDailyBackfillError, match="duplicate observation natural keys"):
        run_daily_demand_backfill(
            client=client,
            session_factory=session_factory,
            importer=lambda *_args: importer_calls.append(True),
        )

    assert importer_calls == []


@pytest.mark.parametrize("response", [None, [None]])
def test_null_response_or_observation_never_calls_importer(response):
    client = FakeClient(response)
    importer_calls = []

    with pytest.raises(NEMDailyBackfillError):
        run_daily_demand_backfill(
            client=client,
            session_factory=session_factory,
            importer=lambda *_args: importer_calls.append(True),
        )

    assert importer_calls == []


def test_api_or_parser_error_is_clear_and_does_not_import():
    client = FakeClient(error=NEMAPIError("Open Electricity API returned an invalid response"))
    importer_calls = []

    with pytest.raises(NEMDailyBackfillError, match="request or response validation failed"):
        run_daily_demand_backfill(
            client=client,
            session_factory=session_factory,
            importer=lambda *_args: importer_calls.append(True),
        )

    assert importer_calls == []


def test_expected_dataset_identity_is_required_before_api_or_import():
    client = FakeClient([demand_record()])
    importer_calls = []

    with pytest.raises(NEMDailyBackfillError, match="Dataset ID 4 was not found"):
        run_daily_demand_backfill(
            client=client,
            session_factory=lambda: FakeSession(SimpleNamespace(
                id=5, name=NEM_DATASET_NAME, source=NEM_DATASET_SOURCE
            )),
            importer=lambda *_args: importer_calls.append(True),
        )

    assert client.calls == []
    assert importer_calls == []


def test_default_importer_is_the_existing_nem_upsert_service(monkeypatch):
    records = [demand_record()]
    client = FakeClient(records)
    calls = []
    expected_history = SimpleNamespace(id=10, dataset_id=4)
    monkeypatch.setattr(
        daily_backfill,
        "import_nem_observations",
        lambda db, batch: calls.append((db, batch)) or expected_history,
    )

    result = run_daily_demand_backfill(client=client, session_factory=session_factory)

    assert result is expected_history
    assert len(calls) == 1
    assert calls[0][1] == records


def test_cli_does_not_log_unexpected_database_credentials(caplog, monkeypatch):
    sensitive_detail = "postgresql://example-user:example-password@db.invalid/example"
    monkeypatch.setattr(
        daily_backfill,
        "run_daily_demand_backfill",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError(sensitive_detail)),
    )

    assert daily_backfill.main(client=FakeClient(), session_factory=session_factory) == 2
    assert sensitive_detail not in caplog.text
    assert "RuntimeError" in caplog.text
