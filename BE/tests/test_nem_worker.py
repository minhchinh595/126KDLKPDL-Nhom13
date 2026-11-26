from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
from threading import Event
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import NEMObservation
from app.nem.client import (
    NEMAPIError,
    NEMHTTPError,
    NEMTimeoutError,
    OpenElectricityClient,
)
from app.nem.schemas import NEMObservationRecord
from app.nem.worker import (
    DAILY_METRICS,
    NEMIngestionWorker,
    WorkerConfig,
    WorkerConfigurationError,
)


class FakeClient:
    def __init__(self, results=None, errors=None):
        self.results = list(results or [])
        self.errors = list(errors or [])
        self.calls = []

    def get_observations(self, *args):
        self.calls.append(args)
        if self.errors:
            error = self.errors.pop(0)
            if error is not None:
                raise error
        return self.results.pop(0) if self.results else []


def make_config(**overrides):
    values = {
        "api_key": "test-key",
        "base_url": "https://api.example.test/v4",
        "timeout_seconds": 4,
        "five_minute_poll_seconds": 300,
        "daily_poll_seconds": 86400,
        "five_minute_lookback_minutes": 30,
        "daily_lookback_days": 3,
    }
    values.update(overrides)
    return WorkerConfig(**values)


def demand_record(at="2026-11-23T00:00:00+11:00", value="42.5"):
    return NEMObservationRecord(
        network_code="NEM",
        metric="demand",
        interval="5m",
        observed_at=datetime.fromisoformat(at),
        value=Decimal(value),
        unit="MW",
        result="demand_total",
        grouping_type="network",
        grouping_code="",
    )


def test_config_defaults_and_rejects_invalid_values(monkeypatch):
    monkeypatch.setenv("OPEN_ELECTRICITY_API_KEY", "test-key")
    for name in (
        "OPEN_ELECTRICITY_BASE_URL",
        "OPEN_ELECTRICITY_API_BASE_URL",
        "OPEN_ELECTRICITY_TIMEOUT_SECONDS",
        "NEM_5M_POLL_SECONDS",
        "NEM_DAILY_POLL_SECONDS",
        "NEM_5M_LOOKBACK_MINUTES",
        "NEM_DAILY_LOOKBACK_DAYS",
    ):
        monkeypatch.delenv(name, raising=False)

    config = WorkerConfig.from_env()
    assert config.base_url == "https://api.openelectricity.org.au/v4"
    assert config.timeout_seconds == 30
    assert config.five_minute_poll_seconds == 300
    assert config.daily_poll_seconds == 86400
    assert config.five_minute_lookback_minutes == 30
    assert config.daily_lookback_days == 3

    for name in ("NEM_5M_POLL_SECONDS", "NEM_DAILY_POLL_SECONDS"):
        monkeypatch.setenv(name, "0")
        with pytest.raises(WorkerConfigurationError, match="positive finite"):
            WorkerConfig.from_env()
        monkeypatch.delenv(name)
    for name in ("NEM_5M_LOOKBACK_MINUTES", "NEM_DAILY_LOOKBACK_DAYS"):
        monkeypatch.setenv(name, "-2")
        with pytest.raises(WorkerConfigurationError, match="positive integer"):
            WorkerConfig.from_env()
        monkeypatch.delenv(name)
    monkeypatch.setenv("OPEN_ELECTRICITY_TIMEOUT_SECONDS", "Infinity")
    with pytest.raises(WorkerConfigurationError, match="positive finite"):
        WorkerConfig.from_env()


def test_missing_api_key_fails_before_client_request():
    client = FakeClient()
    worker = NEMIngestionWorker(make_config(api_key=" "), client=client)
    with pytest.raises(WorkerConfigurationError, match="API_KEY"):
        worker.poll_5m()
    assert client.calls == []


def test_five_minute_window_aligns_boundaries_and_uses_half_open_range():
    client = FakeClient()
    now = datetime.fromisoformat("2026-11-23T13:07:42+11:00")
    worker = NEMIngestionWorker(
        make_config(five_minute_lookback_minutes=30), client=client, clock=lambda: now
    )

    worker.poll_5m()

    network, metrics, interval, start, end, grouping = client.calls[0]
    assert (network, metrics, interval, grouping) == ("NEM", ("demand",), "5m", "network")
    assert start.isoformat() == "2026-11-23T11:35:00+10:00"
    assert end.isoformat() == "2026-11-23T12:05:00+10:00"
    assert start < end <= now


def test_daily_poll_requests_all_metrics_and_excludes_incomplete_local_day():
    client = FakeClient()
    now = datetime.fromisoformat("2026-11-23T08:30:00+11:00")
    worker = NEMIngestionWorker(
        make_config(daily_lookback_days=3), client=client, clock=lambda: now
    )

    worker.poll_daily()

    network, metrics, interval, start, end, grouping = client.calls[0]
    assert network == "NEM"
    assert metrics == DAILY_METRICS
    assert interval == "1d"
    assert grouping == "network"
    assert start.isoformat() == "2026-11-20T00:00:00+10:00"
    assert end.isoformat() == "2026-11-23T00:00:00+10:00"
    assert end.date() == now.date()


@pytest.mark.parametrize(
    ("now", "expected_start", "expected_end"),
    [
        (
            "2026-04-05T12:00:00+10:00",
            "2026-04-02T00:00:00+10:00",
            "2026-04-05T00:00:00+10:00",
        ),
        (
            "2026-10-04T12:00:00+11:00",
            "2026-10-01T00:00:00+10:00",
            "2026-10-04T00:00:00+10:00",
        ),
    ],
)
def test_daily_windows_use_nem_zone_across_sydney_dst_boundaries(now, expected_start, expected_end):
    client = FakeClient()
    worker = NEMIngestionWorker(
        make_config(daily_lookback_days=3),
        client=client,
        clock=lambda: datetime.fromisoformat(now),
    )

    worker.poll_daily()

    start, end = client.calls[0][3:5]
    assert start.isoformat() == expected_start
    assert end.isoformat() == expected_end
    assert start.tzinfo == ZoneInfo("Australia/Brisbane")
    assert end.tzinfo == ZoneInfo("Australia/Brisbane")


def test_empty_response_is_logged_and_does_not_open_database(caplog):
    caplog.set_level("INFO", logger="app.nem.worker")
    client = FakeClient(results=[[]])
    worker = NEMIngestionWorker(
        make_config(),
        client=client,
        session_factory=lambda: pytest.fail("empty response must not open DB"),
        clock=lambda: datetime.now(timezone.utc),
    )

    assert worker.poll_5m() is None
    assert "returned no observations" in caplog.text


def test_transient_http_errors_retry_with_bounded_exponential_backoff():
    sleeps = []
    client = FakeClient(
        results=[[]],
        errors=[NEMHTTPError(503), NEMTimeoutError("safe timeout")],
    )
    worker = NEMIngestionWorker(
        make_config(),
        client=client,
        sleep=sleeps.append,
        clock=lambda: datetime.now(timezone.utc),
    )

    assert worker.poll_5m() is None
    assert len(client.calls) == 3
    assert sleeps == [1.0, 2.0]


def test_transient_retries_stop_after_configured_attempt_limit():
    sleeps = []
    client = FakeClient(errors=[NEMHTTPError(503), NEMHTTPError(429), NEMHTTPError(500)])
    worker = NEMIngestionWorker(
        make_config(),
        client=client,
        sleep=sleeps.append,
        clock=lambda: datetime.now(timezone.utc),
    )

    with pytest.raises(NEMHTTPError):
        worker.poll_5m()
    assert len(client.calls) == 3
    assert sleeps == [1.0, 2.0]


def test_invalid_api_response_is_not_retried():
    sleeps = []
    client = FakeClient(errors=[NEMAPIError("invalid response")])
    worker = NEMIngestionWorker(
        make_config(),
        client=client,
        sleep=sleeps.append,
        clock=lambda: datetime.now(timezone.utc),
    )

    with pytest.raises(NEMAPIError):
        worker.poll_5m()
    assert len(client.calls) == 1
    assert sleeps == []


def test_scheduler_logs_poll_error_and_still_runs_other_due_job(monkeypatch, caplog):
    caplog.set_level("ERROR", logger="app.nem.worker")
    worker = NEMIngestionWorker(
        make_config(),
        client=FakeClient(),
        clock=lambda: datetime.now(timezone.utc),
    )
    daily_calls = []

    def fail_poll():
        raise NEMAPIError("safe invalid payload")

    monkeypatch.setattr(worker, "poll_5m", fail_poll)
    monkeypatch.setattr(worker, "poll_daily", lambda: daily_calls.append(True))

    assert worker.run_iteration() == {"5m": True, "1d": True}
    assert daily_calls == [True]
    assert "NEM 5m poll failed (NEMAPIError)" in caplog.text


def test_session_closes_after_persistence_success_and_failure(monkeypatch):
    class Session:
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.closed = True

    success_session = Session()
    monkeypatch.setattr(
        "app.nem.worker.import_nem_observations",
        lambda _db, records: type(
            "History", (), {"rows_read": len(records), "inserted_count": 1, "updated_count": 0, "skipped_count": 0}
        )(),
    )
    worker = NEMIngestionWorker(
        make_config(),
        client=FakeClient(results=[[demand_record()]]),
        session_factory=lambda: success_session,
        clock=lambda: datetime.now(timezone.utc),
    )
    worker.poll_5m()
    assert success_session.closed

    failure_session = Session()
    monkeypatch.setattr(
        "app.nem.worker.import_nem_observations",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("safe failure")),
    )
    worker = NEMIngestionWorker(
        make_config(),
        client=FakeClient(results=[[demand_record()]]),
        session_factory=lambda: failure_session,
        clock=lambda: datetime.now(timezone.utc),
    )
    with pytest.raises(RuntimeError):
        worker.poll_5m()
    assert failure_session.closed


def test_scheduler_runs_only_jobs_that_are_due(monkeypatch):
    now = [datetime(2026, 11, 23, tzinfo=timezone.utc)]
    calls = []
    worker = NEMIngestionWorker(make_config(), client=FakeClient(), clock=lambda: now[0])
    monkeypatch.setattr(worker, "poll_5m", lambda: calls.append("5m"))
    monkeypatch.setattr(worker, "poll_daily", lambda: calls.append("1d"))

    assert worker.run_iteration() == {"5m": True, "1d": True}
    assert calls == ["5m", "1d"]
    calls.clear()
    now[0] += timedelta(seconds=10)
    assert worker.run_iteration() == {"5m": False, "1d": False}
    assert calls == []
    now[0] += timedelta(seconds=300)
    assert worker.run_iteration() == {"5m": True, "1d": False}
    assert calls == ["5m"]


def test_repeated_polls_are_idempotent(test_engine):
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    now = datetime.fromisoformat("2026-11-23T13:07:42+11:00")
    client = FakeClient(results=[[demand_record()], [demand_record()]])
    worker = NEMIngestionWorker(
        make_config(), client=client, session_factory=factory, clock=lambda: now
    )

    first = worker.poll_5m()
    second = worker.poll_5m()

    assert first.inserted_count == 1
    assert second.inserted_count == 0
    assert second.skipped_count == 1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(NEMObservation)) == 1


def test_checked_in_response_flows_through_parser_worker_and_import_service(test_engine):
    sample_path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "raw"
        / "openelectricity"
        / "nem"
        / "market"
        / "snapshot_2026-11-23_demand_5m.json"
    )
    payload = json.loads(sample_path.read_text(encoding="utf-8-sig"))
    payload["data"][0]["results"][0]["data"] = payload["data"][0]["results"][0]["data"][:2]

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(payload).encode()

    client = OpenElectricityClient(
        base_url="https://api.example.test/v4",
        api_key="test-key",
        opener=lambda *_args, **_kwargs: Response(),
    )
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    worker = NEMIngestionWorker(
        make_config(),
        client=client,
        session_factory=factory,
        clock=lambda: datetime.fromisoformat("2026-11-23T00:12:42+11:00"),
    )

    imported = worker.poll_5m()

    assert imported.status == "completed"
    assert imported.inserted_count == 2
    with factory() as db:
        rows = db.scalars(select(NEMObservation).order_by(NEMObservation.observed_at)).all()
        assert [row.value for row in rows] == [Decimal("20628.55"), Decimal("20454.21")]
        assert all(row.unit == "MW" for row in rows)


def test_concurrent_polls_do_not_overlap():
    entered = Event()
    release = Event()

    class BlockingClient(FakeClient):
        def get_observations(self, *args):
            self.calls.append(args)
            entered.set()
            assert release.wait(timeout=3)
            return []

    client = BlockingClient()
    worker = NEMIngestionWorker(
        make_config(), client=client, clock=lambda: datetime.now(timezone.utc)
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(worker.poll_5m)
        assert entered.wait(timeout=2)
        second = pool.submit(worker.poll_daily)
        assert second.result(timeout=2) is None
        release.set()
        assert first.result(timeout=2) is None
    assert len(client.calls) == 1


def test_run_loop_stops_cleanly_on_keyboard_interrupt():
    def interrupt(_seconds):
        raise KeyboardInterrupt

    worker = NEMIngestionWorker(
        make_config(), client=FakeClient(), sleep=interrupt,
        clock=lambda: datetime.now(timezone.utc),
    )
    worker.run()
