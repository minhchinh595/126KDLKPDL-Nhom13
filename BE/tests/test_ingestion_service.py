import csv
import io
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.ingestion.pipeline import normalize_csv
from app.ingestion.reader import parse_csv_bytes
from app.ingestion.date_utils import parse_month
from service_apps.ingestion import main as ingestion_service


SECRET = "ingestion-unit-test-secret-with-at-least-32-bytes"
HEADERS = {"X-Ingestion-Service-Secret": SECRET}
CSV_HEADER = "country_id,country,iso3,month,metric,fuel,value,unit\n"


def csv_bytes(rows: list[list[str]], *, bom: bool = False) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(CSV_HEADER.rstrip("\n").split(","))
    writer.writerows(rows)
    content = output.getvalue().encode("utf-8")
    return (b"\xef\xbb\xbf" + content) if bom else content


VALID_ROW = ["vietnam", "Vietnam", "vnm", "2026-09", "demand", "", "17.8700", "TWh"]


def test_parser_accepts_utf8_bom_and_normalizes_monthly_record():
    result = normalize_csv(csv_bytes([VALID_ROW], bom=True))
    assert result["rows_read"] == 1
    assert result["start_month"].isoformat() == "2026-09-01"
    assert result["end_month"] == result["start_month"]
    row = result["rows"][0]
    assert row["country_id"] == "vietnam"
    assert row["iso3"] == "VNM" and row["fuel"] is None
    assert row["month"] == result["start_month"]
    assert row["value"] == Decimal("17.8700")


def test_shared_month_parser_accepts_yyyy_mm_and_rejects_other_formats():
    assert parse_month("2026-09").isoformat() == "2026-09-01"
    for value in ("2026-13", "2026-9", "2026-W01", "2026-09-01"):
        with pytest.raises(ValueError, match="YYYY-MM"):
            parse_month(value)


@pytest.mark.parametrize(
    "content,expected",
    [
        (b"", "Missing required columns"),
        (b"a,b\n1,2\n", "Missing required columns"),
        (b"country_id,country,iso3,month,metric,fuel,value,value\nx,1,VNM,2026-09,demand,,1,TWh\n", "CSV headers must be present and unique"),
        (CSV_HEADER.encode() + b"x,1,VNM,2026-09,demand,,1,TWh,extra\n", "row contains more values"),
        (csv_bytes([["vietnam", "Vietnam", "VNM", "2026-13", "demand", "", "1", "TWh"]]), "CSV validation failed"),
        (csv_bytes([["vietnam", "Vietnam", "VNM", "2026-W01", "demand", "", "1", "TWh"]]), "CSV validation failed"),
        (csv_bytes([["vietnam", "Vietnam", "VNM", "2026-09", "demand", "", "-1", "TWh"]]), "CSV validation failed"),
        (csv_bytes([["vietnam", "Vietnam", "VNM", "2026-09", "demand", "", "NaN", "TWh"]]), "CSV validation failed"),
        (csv_bytes([["vietnam", "Vietnam", "VNM", "2026-09", "demand", "", "123456789012345", "TWh"]]), "CSV validation failed"),
        (csv_bytes([["vietnam", "Vietnam", "USA", "2026-09", "demand", "", "1", "TWh"]]), "CSV validation failed"),
        (csv_bytes([["vietnam", "Vietnam", "VNM", "2026-09", "generation", "", "1", "TWh"]]), "CSV validation failed"),
        (csv_bytes([["vietnam", "Vietnam", "VNM", "2026-09", "demand", "coal", "1", "TWh"]]), "CSV validation failed"),
        (csv_bytes([["vietnam", "Vietnam", "VNM", "2026-09", "demand", "", "1", "GWh"]]), "CSV validation failed"),
        (csv_bytes([VALID_ROW, VALID_ROW]), "duplicate natural key"),
        (csv_bytes([]), "CSV contains no data rows"),
    ],
)
def test_parser_rejects_invalid_csv(content, expected):
    with pytest.raises(ValueError, match=expected):
        parse_csv_bytes(content)


def test_ingestion_service_health_auth_and_normalize(monkeypatch):
    monkeypatch.setenv("INGESTION_SERVICE_SECRET", SECRET)
    client = TestClient(ingestion_service.app)
    assert client.get("/health").json() == {"status": "success", "service": "ingestion"}
    assert client.post(
        "/internal/ingestion/normalize", files={"file": ("data.csv", csv_bytes([VALID_ROW]))}
    ).status_code == 401
    assert client.post(
        "/internal/ingestion/normalize",
        files={"file": ("data.csv", csv_bytes([VALID_ROW]))},
        headers={"X-Ingestion-Service-Secret": "wrong"},
    ).status_code == 401

    response = client.post(
        "/internal/ingestion/normalize",
        files={"file": ("data.csv", csv_bytes([VALID_ROW]))},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["rows_read"] == 1
    assert payload["start_month"] == "2026-09-01"
    assert payload["rows"][0]["iso3"] == "VNM"
    assert payload["rows"][0]["fuel"] is None
    assert payload["rows"][0]["value"] == "17.8700"


def test_ingestion_service_rejects_invalid_csv_and_non_csv(monkeypatch):
    monkeypatch.setenv("INGESTION_SERVICE_SECRET", SECRET)
    client = TestClient(ingestion_service.app)
    invalid = client.post(
        "/internal/ingestion/normalize",
        files={"file": ("data.csv", b"not,a,valid,csv\n")},
        headers=HEADERS,
    )
    assert invalid.status_code == 422
    assert "Traceback" not in invalid.text
    assert str(ingestion_service.__file__) not in invalid.text
    non_csv = client.post(
        "/internal/ingestion/normalize",
        files={"file": ("data.txt", csv_bytes([VALID_ROW]))},
        headers=HEADERS,
    )
    assert non_csv.status_code == 415


def test_ingestion_service_enforces_upload_limit(monkeypatch):
    monkeypatch.setenv("INGESTION_SERVICE_SECRET", SECRET)
    monkeypatch.setattr(ingestion_service, "MAX_UPLOAD_BYTES", 10)
    client = TestClient(ingestion_service.app)
    response = client.post(
        "/internal/ingestion/normalize",
        files={"file": ("data.csv", b"x" * 11)},
        headers=HEADERS,
    )
    assert response.status_code == 413


def test_ingestion_service_reports_unconfigured_internal_secret(monkeypatch):
    monkeypatch.setenv("INGESTION_SERVICE_SECRET", "short")
    client = TestClient(ingestion_service.app)
    response = client.post(
        "/internal/ingestion/normalize",
        files={"file": ("data.csv", csv_bytes([VALID_ROW]))},
        headers=HEADERS,
    )
    assert response.status_code == 503
