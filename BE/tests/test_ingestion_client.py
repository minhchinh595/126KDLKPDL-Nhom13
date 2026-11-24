import json
from datetime import date
from decimal import Decimal
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from app.clients.ingestion import (
    IngestionFileTooLarge,
    IngestionServiceClient,
    IngestionServiceRejected,
    IngestionServiceUnavailable,
)


SECRET = "ingestion-client-unit-test-secret-at-least-32-bytes"
CONTENT = b"country_id,country,iso3,month,metric,fuel,value,unit\nvietnam,Vietnam,VNM,2026-09,demand,,17.87,TWh\n"
RESULT = {
    "rows": [{
        "country_id": "vietnam", "country": "Vietnam", "iso3": "VNM",
        "month": "2026-09-01", "metric": "demand", "fuel": None,
        "value": "17.8700", "unit": "TWh",
    }],
    "rows_read": 1,
    "start_month": "2026-09-01",
    "end_month": "2026-09-01",
}


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self.payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def test_ingestion_client_sends_multipart_and_internal_secret():
    captured = []

    def opener(request, timeout):
        captured.append((request, timeout))
        return FakeResponse(RESULT)

    client = IngestionServiceClient(
        base_url="http://ingestion.internal:8105/",
        secret=SECRET,
        timeout_seconds=17,
        opener=opener,
    )
    parsed = client.normalize(CONTENT)
    request, timeout = captured[0]
    assert request.full_url == "http://ingestion.internal:8105/internal/ingestion/normalize"
    assert request.get_header("X-ingestion-service-secret") == SECRET
    assert request.get_header("Content-type").startswith("multipart/form-data; boundary=")
    assert b'filename="upload.csv"' in request.data
    assert CONTENT in request.data
    assert timeout == 17
    assert parsed.rows_read == 1
    assert parsed.start_month == date(2026, 9, 1)
    assert parsed.rows[0]["value"] == Decimal("17.8700")


def test_ingestion_client_maps_service_statuses():
    cases = [
        (413, b'{"detail":"too large"}', IngestionFileTooLarge),
        (422, b'{"detail":"CSV validation failed: bad month"}', IngestionServiceRejected),
        (500, b'{"detail":"private traceback"}', IngestionServiceUnavailable),
    ]
    for status, body, error_type in cases:
        client = IngestionServiceClient(
            secret=SECRET, opener=lambda *_args, **_kwargs: FakeResponse(body, status=status)
        )
        with pytest.raises(error_type) as error:
            client.normalize(CONTENT)
        assert "private traceback" not in str(error.value)


def test_ingestion_client_maps_http_errors_and_network_failures():
    def http_error(request, timeout):
        raise HTTPError(request.full_url, 422, "invalid", None, BytesIO(b'{"detail":"bad month"}'))

    invalid_client = IngestionServiceClient(secret=SECRET, opener=http_error)
    with pytest.raises(IngestionServiceRejected, match="bad month"):
        invalid_client.normalize(CONTENT)

    disconnected = IngestionServiceClient(
        secret=SECRET, opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("private"))
    )
    with pytest.raises(IngestionServiceUnavailable, match="unavailable"):
        disconnected.normalize(CONTENT)


def test_ingestion_client_maps_opener_value_error_without_leaking_request_details():
    sensitive_url = "https://private-user:private-password@internal.example"

    def invalid_request(_request, timeout):
        raise ValueError(f"Invalid URL {sensitive_url}; secret={SECRET}")

    client = IngestionServiceClient(
        base_url=sensitive_url,
        secret=SECRET,
        opener=invalid_request,
    )
    with pytest.raises(IngestionServiceUnavailable) as error:
        client.normalize(CONTENT)
    assert str(error.value) == "Ingestion Service is unavailable"
    assert sensitive_url not in str(error.value)
    assert SECRET not in str(error.value)


@pytest.mark.parametrize("timeout", ["", "bad", "NaN", "Infinity", "0", "-1"])
def test_ingestion_client_rejects_invalid_timeout(monkeypatch, timeout):
    monkeypatch.setenv("INGESTION_SERVICE_TIMEOUT_SECONDS", timeout)
    called = []
    client = IngestionServiceClient(secret=SECRET, opener=lambda *_a, **_k: called.append(True))
    with pytest.raises(IngestionServiceUnavailable, match="timeout"):
        client.normalize(CONTENT)
    assert called == []


@pytest.mark.parametrize(
    "payload",
    [
        {"rows": RESULT["rows"], "rows_read": 1, "start_month": "2026-09-01"},
        {**RESULT, "rows_read": "1"},
        {**RESULT, "rows": [{**RESULT["rows"][0], "month": "2026-09"}]},
        {**RESULT, "rows": [{**RESULT["rows"][0], "value": 17.87}]},
        {**RESULT, "rows": [{**RESULT["rows"][0], "fuel": "coal"}]},
        {**RESULT, "end_month": "2026-10-01"},
    ],
)
def test_ingestion_client_rejects_invalid_response_contract(payload):
    client = IngestionServiceClient(
        secret=SECRET, opener=lambda *_args, **_kwargs: FakeResponse(payload)
    )
    with pytest.raises(IngestionServiceUnavailable, match="invalid response"):
        client.normalize(CONTENT)


def test_ingestion_client_rejects_malformed_json_and_does_not_log_secret(caplog):
    client = IngestionServiceClient(
        secret=SECRET, opener=lambda *_args, **_kwargs: FakeResponse(b"not-json")
    )
    with pytest.raises(IngestionServiceUnavailable):
        client.normalize(CONTENT)
    assert SECRET not in caplog.text
