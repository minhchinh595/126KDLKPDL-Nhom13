import copy
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from app.nem.client import (
    NEMAPIError,
    NEMConfigurationError,
    NEMConnectionError,
    NEMHTTPError,
    NEMTimeoutError,
    OpenElectricityClient,
)
from app.nem.schemas import (
    NEMAPIRejected,
    NEMResponseValidationError,
    parse_response,
)


API_KEY = "unit-test-key-never-used-for-network-access"
START = datetime(2026, 11, 23, 0, 0, tzinfo=timezone(timedelta(hours=10)))
END = datetime(2026, 11, 24, 0, 0, tzinfo=timezone(timedelta(hours=10)))
SAMPLE_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "raw"
    / "openelectricity"
    / "nem"
    / "market"
    / "snapshot_2026-11-23_demand_5m.json"
)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self.body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


@pytest.fixture
def sample_payload():
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8-sig"))


def _client(payload, *, opener=None, **kwargs):
    if opener is None:
        opener = lambda *_args, **_kwargs: FakeResponse(payload)
    return OpenElectricityClient(
        base_url="https://api.example.test/v4",
        api_key=API_KEY,
        opener=opener,
        **kwargs,
    )


def test_parse_checked_in_nem_response(sample_payload):
    records = parse_response(
        sample_payload,
        expected_network_code="NEM",
        expected_metrics=["demand"],
        expected_interval="5m",
    )

    assert len(records) == 288
    assert records[0].network_code == "NEM"
    assert records[0].metric == "demand"
    assert records[0].interval == "5m"
    assert records[0].observed_at.isoformat() == "2026-11-23T00:00:00+10:00"
    assert records[0].value == Decimal("20628.55")
    assert records[0].unit == "MW"
    assert records[0].result == "demand_total"
    assert records[0].grouping_type == "network"
    assert records[0].grouping_code == ""
    assert records[0].as_dict()["value"] == Decimal("20628.55")


def test_client_builds_get_request_and_repeats_metrics(sample_payload):
    captured = []
    multi_payload = {"success": True, "data": []}
    for metric, unit, result in (
        ("demand", "MW", "demand_total"),
        ("price", "API-reported-unit", "price_result"),
    ):
        series = copy.deepcopy(sample_payload["data"][0])
        series.update(metric=metric, interval="1d", unit=unit)
        series["results"][0].update(
            name=result,
            data=[["2026-11-23T00:00:00+10:00", 123.25]],
        )
        multi_payload["data"].append(series)

    def opener(request, timeout):
        captured.append((request, timeout))
        return FakeResponse(multi_payload)

    client = _client(multi_payload, opener=opener, timeout_seconds=12.5)
    records = client.get_observations(
        "NEM", ["demand", "price"], "1d", START, END, "network"
    )

    request, timeout = captured[0]
    query = parse_qs(urlsplit(request.full_url).query)
    assert request.full_url.startswith(
        "https://api.example.test/v4/market/network/NEM?"
    )
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") == f"Bearer {API_KEY}"
    assert query["metrics"] == ["demand", "price"]
    assert query["interval"] == ["1d"]
    assert query["date_start"] == ["2026-11-23T00:00:00"]
    assert query["date_end"] == ["2026-11-24T00:00:00"]
    assert query["primary_grouping"] == ["network"]
    assert request.get_header("User-agent") == "DoAn-KhoDuLieu-NEM-Ingestion/0.1 (Python)"
    assert timeout == 12.5
    assert [record.metric for record in records] == ["demand", "price"]
    assert records[1].unit == "API-reported-unit"
    assert records[1].result == "price_result"


def test_client_converts_utc_instants_to_timezone_naive_brisbane_query(sample_payload):
    captured = []
    client = _client(sample_payload, opener=lambda request, **_: (captured.append(request) or FakeResponse(sample_payload)))
    utc_start = datetime.fromisoformat("2026-11-22T14:00:00+00:00")
    utc_end = datetime.fromisoformat("2026-11-23T14:00:00+00:00")

    client.get_observations("NEM", ["demand"], "5m", utc_start, utc_end)

    query = parse_qs(urlsplit(captured[0].full_url).query)
    assert query["date_start"] == ["2026-11-23T00:00:00"]
    assert query["date_end"] == ["2026-11-24T00:00:00"]


def test_client_prefers_compose_base_url_environment_variable(monkeypatch, sample_payload):
    monkeypatch.setenv("OPEN_ELECTRICITY_BASE_URL", "https://compose.example.test/v4")
    monkeypatch.setenv("OPEN_ELECTRICITY_API_BASE_URL", "https://legacy.example.test/v4")
    monkeypatch.setenv("OPEN_ELECTRICITY_API_KEY", API_KEY)
    captured = []
    client = OpenElectricityClient(opener=lambda request, **_: (captured.append(request) or FakeResponse(sample_payload)))

    client.get_observations("NEM", ["demand"], "5m", START, END)

    assert captured[0].full_url.startswith("https://compose.example.test/v4/")


def test_client_supports_legacy_base_url_environment_alias(monkeypatch, sample_payload):
    monkeypatch.delenv("OPEN_ELECTRICITY_BASE_URL", raising=False)
    monkeypatch.setenv("OPEN_ELECTRICITY_API_BASE_URL", "https://legacy.example.test/v4")
    monkeypatch.setenv("OPEN_ELECTRICITY_API_KEY", API_KEY)
    captured = []
    client = OpenElectricityClient(opener=lambda request, **_: (captured.append(request) or FakeResponse(sample_payload)))

    client.get_observations("NEM", ["demand"], "5m", START, END)

    assert captured[0].full_url.startswith("https://legacy.example.test/v4/")


def test_client_does_not_fetch_without_api_key(monkeypatch, sample_payload):
    monkeypatch.delenv("OPEN_ELECTRICITY_API_KEY", raising=False)
    calls = []
    client = OpenElectricityClient(
        base_url="https://api.example.test/v4",
        opener=lambda *_args, **_kwargs: calls.append(True),
    )

    with pytest.raises(NEMConfigurationError, match="OPEN_ELECTRICITY_API_KEY"):
        client.get_observations("NEM", ["demand"], "5m", START, END)
    assert calls == []


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_client_maps_http_errors_without_exposing_response_body(status, sample_payload):
    def opener(request, timeout):
        raise HTTPError(
            request.full_url,
            status,
            "private error body",
            None,
            BytesIO(b"private response details"),
        )

    client = _client(sample_payload, opener=opener)
    with pytest.raises(NEMHTTPError) as error:
        client.get_observations("NEM", ["demand"], "5m", START, END)
    assert error.value.status_code == status
    assert "private response details" not in str(error.value)
    assert API_KEY not in str(error.value)


def test_client_maps_timeout_and_connection_failure(sample_payload):
    timeout_client = _client(
        sample_payload,
        opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("private")),
    )
    with pytest.raises(NEMTimeoutError, match="timed out"):
        timeout_client.get_observations("NEM", ["demand"], "5m", START, END)

    connection_client = _client(
        sample_payload,
        opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("private host")),
    )
    with pytest.raises(NEMConnectionError, match="Could not connect") as error:
        connection_client.get_observations("NEM", ["demand"], "5m", START, END)
    assert "private host" not in str(error.value)
    assert API_KEY not in str(error.value)


def test_client_rejects_invalid_json_and_success_false(sample_payload):
    invalid_json = _client(sample_payload, opener=lambda *_a, **_k: FakeResponse(b"not-json"))
    with pytest.raises(NEMAPIError, match="invalid JSON"):
        invalid_json.get_observations("NEM", ["demand"], "5m", START, END)

    rejected_payload = {"success": False, "error": "private API detail"}
    rejected = _client(rejected_payload)
    with pytest.raises(NEMAPIError, match="success=false") as error:
        rejected.get_observations("NEM", ["demand"], "5m", START, END)
    assert "private API detail" not in str(error.value)


def test_parser_rejects_missing_metric_series(sample_payload):
    with pytest.raises(NEMResponseValidationError, match="no metric series"):
        parse_response({"success": True, "data": []}, expected_metrics=["demand"])

    wrong_metric = copy.deepcopy(sample_payload)
    wrong_metric["data"][0]["metric"] = "price"
    wrong_metric["data"][0]["interval"] = "1d"
    with pytest.raises(NEMResponseValidationError, match="missing requested metric"):
        parse_response(
            wrong_metric,
            expected_network_code="NEM",
            expected_metrics=["demand"],
            expected_interval="1d",
        )


def test_parser_rejects_naive_timestamp(sample_payload):
    sample_payload["data"][0]["results"][0]["data"][0][0] = "2026-11-23T00:00:00"
    with pytest.raises(NEMResponseValidationError, match="timezone offset"):
        parse_response(sample_payload)


def test_parser_skips_null_observation_values(sample_payload):
    sample_payload["data"][0]["results"][0]["data"][0][1] = None

    records = parse_response(sample_payload)

    assert len(records) == 287
    assert all(record.value is not None for record in records)
    assert records[0].observed_at.isoformat() == "2026-11-23T00:05:00+10:00"


@pytest.mark.parametrize("bad_value", ["not-numeric", "NaN", "Infinity", True])
def test_parser_rejects_non_numeric_or_non_finite_values(sample_payload, bad_value):
    sample_payload["data"][0]["results"][0]["data"][0][1] = bad_value
    with pytest.raises(NEMResponseValidationError, match="numeric|finite"):
        parse_response(sample_payload)


def test_parser_rejects_invalid_metric_interval_unit_result_and_grouping(sample_payload):
    bad_metric = copy.deepcopy(sample_payload)
    bad_metric["data"][0]["metric"] = "unknown"
    with pytest.raises(NEMResponseValidationError, match="not supported"):
        parse_response(bad_metric)

    bad_interval = copy.deepcopy(sample_payload)
    bad_interval["data"][0]["interval"] = "1w"
    with pytest.raises(NEMResponseValidationError, match="unsupported response interval"):
        parse_response(bad_interval)

    bad_unit = copy.deepcopy(sample_payload)
    bad_unit["data"][0]["unit"] = "TWh"
    with pytest.raises(NEMResponseValidationError, match="observed contract"):
        parse_response(bad_unit)

    bad_result = copy.deepcopy(sample_payload)
    bad_result["data"][0]["results"][0]["name"] = ""
    with pytest.raises(NEMResponseValidationError, match="result name"):
        parse_response(bad_result)

    bad_grouping = copy.deepcopy(sample_payload)
    with pytest.raises(NEMResponseValidationError, match="region grouping value"):
        parse_response(bad_grouping, primary_grouping="network_region")


def test_parser_preserves_negative_values_and_does_not_convert_timezone(sample_payload):
    sample_payload["data"][0]["results"][0]["data"][0][1] = -1.25
    record = parse_response(sample_payload)[0]
    assert record.value == Decimal("-1.25")
    assert record.observed_at.utcoffset() == timedelta(hours=10)


def test_parser_accepts_multiple_grouped_result_series(sample_payload):
    series = sample_payload["data"][0]
    series["groupings"] = ["network_region"]
    first = copy.deepcopy(series["results"][0])
    second = copy.deepcopy(first)
    first["columns"] = {"region": "NSW1"}
    second["columns"] = {"region": "VIC1"}
    second["name"] = "demand_vic"
    series["results"] = [first, second]

    records = parse_response(sample_payload, primary_grouping="network_region")

    assert len(records) == 576
    assert {record.grouping_type for record in records} == {"network_region"}
    assert {record.grouping_code for record in records} == {"NSW1", "VIC1"}


def test_parser_rejects_malformed_grouping_metadata(sample_payload):
    sample_payload["data"][0]["groupings"] = {"network_region": "NSW1"}
    with pytest.raises(NEMResponseValidationError, match="groupings must be a list"):
        parse_response(sample_payload)


@pytest.mark.parametrize(
    "start,end",
    [
        (datetime(2026, 11, 23), END),
        (START, datetime(2026, 11, 24)),
        (END, START),
        (START, START),
    ],
)
def test_client_rejects_naive_or_invalid_date_ranges(sample_payload, start, end):
    client = _client(sample_payload, opener=lambda *_args, **_kwargs: pytest.fail("network call"))
    with pytest.raises(NEMResponseValidationError):
        client.get_observations("NEM", ["demand"], "5m", start, end)


@pytest.mark.parametrize("timeout", ["", "bad", "NaN", "Infinity", "0", "-1"])
def test_client_rejects_invalid_timeout_without_network_call(monkeypatch, sample_payload, timeout):
    monkeypatch.setenv("OPEN_ELECTRICITY_TIMEOUT_SECONDS", timeout)
    client = OpenElectricityClient(
        base_url="https://api.example.test/v4",
        api_key=API_KEY,
        opener=lambda *_args, **_kwargs: pytest.fail("network call"),
    )
    with pytest.raises(NEMConfigurationError, match="TIMEOUT_SECONDS"):
        client.get_observations("NEM", ["demand"], "5m", START, END)
