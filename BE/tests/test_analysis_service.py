import json
from datetime import date
from pathlib import Path
from urllib.error import URLError

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.analysis.statistics import build_summary
from app.main import app as gateway_app
from app.clients.analysis import AnalysisServiceClient, AnalysisServiceUnavailable
from app.api.routes import analysis as analysis_gateway
from scripts.import_electricity_data import load_rows
from service_apps.analysis.auth import require_analysis_service_secret
from service_apps.analysis.main import app, correlation, distribution, health_check, seasonality, summary, trend
from service_apps.analysis.schemas import AnalysisRecordsRequest, DistributionRequest, TrendRequest


@pytest.fixture
def monthly_records():
    csv_path = Path(__file__).resolve().parents[2] / "data" / "processed" / "vietnam_electricity_demand.csv"
    return [{"month": row["month"].strftime("%Y-%m"), "value": float(row["value"])} for row in load_rows(csv_path)]


def test_analysis_service_reuses_existing_algorithms(monthly_records):
    payload = AnalysisRecordsRequest(records=monthly_records)
    summary_result = summary(payload)
    assert summary_result["count"] == 93
    assert summary_result["start_month"] == "2019-01"
    assert summary_result["end_month"] == "2026-09"
    assert summary_result["mean"] == build_summary(monthly_records)["mean"]

    trend_result = trend(TrendRequest(records=monthly_records, window_months=6))
    assert trend_result["window_months"] == 6
    assert trend_result["records"][-1]["month"] == "2026-09"

    seasonality_result = seasonality(payload)
    correlation_result = correlation(payload)
    assert len(seasonality_result["records"]) == 12
    assert correlation_result["features"] == ["demand", "previous_month", "previous_year"]

    distribution_result = distribution(DistributionRequest(records=monthly_records, bins=8))
    assert distribution_result["count"] == 93
    assert sum(item["count"] for item in distribution_result["bins"]) == 93


def test_analysis_service_validates_records_and_options(monthly_records):
    duplicate = [*monthly_records, monthly_records[0]]
    with pytest.raises(ValueError, match="duplicate months"):
        AnalysisRecordsRequest(records=duplicate)
    with pytest.raises(ValueError):
        AnalysisRecordsRequest(records=[{"month": "2026-13", "value": 1}])
    with pytest.raises(ValueError):
        TrendRequest(records=monthly_records, window_months=1)
    with pytest.raises(ValueError):
        DistributionRequest(records=monthly_records, bins=51)


def test_analysis_service_http_auth_validation_and_response(monthly_records, monkeypatch):
    secret = "analysis-test-secret-with-at-least-32-bytes"
    monkeypatch.setenv("ANALYSIS_SERVICE_SECRET", secret)
    client = TestClient(app)

    assert client.get("/health").status_code == 200
    unauthenticated = client.post("/internal/analysis/summary", json={"records": monthly_records})
    assert unauthenticated.status_code == 401

    response = client.post(
        "/internal/analysis/summary",
        json={"records": monthly_records},
        headers={"X-Analysis-Service-Secret": secret},
    )
    assert response.status_code == 200, response.text
    assert response.json()["count"] == 93
    assert response.json()["start_month"] == "2019-01"

    invalid = client.post(
        "/internal/analysis/trend",
        json={"records": monthly_records, "window_months": 1},
        headers={"X-Analysis-Service-Secret": secret},
    )
    assert invalid.status_code == 422


def test_analysis_service_internal_auth_and_health(monkeypatch):
    secret = "analysis-test-secret-with-at-least-32-bytes"
    monkeypatch.setenv("ANALYSIS_SERVICE_SECRET", secret)
    assert require_analysis_service_secret(secret) is None
    with pytest.raises(HTTPException) as unauthorized:
        require_analysis_service_secret("wrong")
    assert unauthorized.value.status_code == 401
    monkeypatch.delenv("ANALYSIS_SERVICE_SECRET")
    with pytest.raises(HTTPException) as unconfigured:
        require_analysis_service_secret(secret)
    assert unconfigured.value.status_code == 503
    assert health_check() == {"status": "success", "service": "analysis"}

    openapi_paths = app.openapi()["paths"]
    assert "/health" in openapi_paths
    assert "/internal/analysis/summary" in openapi_paths
    assert "/internal/analysis/trend" in openapi_paths
    assert "/internal/analysis/seasonality" in openapi_paths
    assert "/internal/analysis/correlation" in openapi_paths
    assert "/internal/analysis/distribution" in openapi_paths


def test_gateway_openapi_preserves_analysis_public_contract():
    schema = gateway_app.openapi()
    expected = {
        "/api/analysis/summary": ("SummaryResponse", {"start_month", "end_month"}),
        "/api/analysis/trend": ("TrendResponse", {"start_month", "end_month", "window_months"}),
        "/api/analysis/seasonality": ("SeasonalityResponse", {"start_month", "end_month"}),
        "/api/analysis/correlation": ("CorrelationResponse", {"start_month", "end_month"}),
        "/api/analysis/distribution": ("DistributionResponse", {"start_month", "end_month", "bins"}),
    }
    for path, (response_name, expected_parameters) in expected.items():
        operation = schema["paths"][path]["get"]
        assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(response_name)
        assert expected_parameters <= {parameter["name"] for parameter in operation["parameters"]}
        assert operation["security"]


def test_gateway_client_posts_secret_records_and_timeout(monthly_records):
    captured = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"count": 93}).encode()

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["secret"] = request.get_header("X-analysis-service-secret")
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response()

    client = AnalysisServiceClient(
        base_url="http://analysis.internal:8101/",
        secret="analysis-test-secret-with-at-least-32-bytes",
        timeout_seconds=2.5,
        opener=opener,
    )
    assert client.analyze("summary", monthly_records) == {"count": 93}
    assert captured["url"] == "http://analysis.internal:8101/internal/analysis/summary"
    assert captured["secret"] == "analysis-test-secret-with-at-least-32-bytes"
    assert captured["payload"]["records"] == monthly_records
    assert captured["timeout"] == 2.5


def test_gateway_client_hides_upstream_failure_details(monthly_records):
    def unavailable(_request, timeout):
        raise URLError("private-host-and-secret-must-not-leak")

    client = AnalysisServiceClient(
        base_url="http://private-analysis:8101",
        secret="analysis-test-secret-with-at-least-32-bytes",
        opener=unavailable,
    )
    with pytest.raises(AnalysisServiceUnavailable) as error:
        client.analyze("summary", monthly_records)
    assert "private-host" not in str(error.value)
    assert "secret" not in str(error.value)

    with pytest.raises(AnalysisServiceUnavailable, match="cannot be serialized"):
        client.analyze("summary", [{"month": "2026-09", "value": float("nan")}])


def test_gateway_maps_unavailable_service_to_non_sensitive_503(monkeypatch, monthly_records):
    def unavailable(*_args, **_kwargs):
        raise AnalysisServiceUnavailable("private url and secret")

    monkeypatch.setattr(analysis_gateway.analysis_service_client, "analyze", unavailable)
    with pytest.raises(HTTPException) as error:
        analysis_gateway._analyze("summary", monthly_records)
    assert error.value.status_code == 503
    assert error.value.detail == "Analysis service is unavailable"
    assert "private" not in error.value.detail


def test_public_gateway_handler_forwards_db_records_and_options(monkeypatch):
    from app.api.routes import analysis as routes

    class Row:
        def __init__(self, month, value):
            self.month = month
            self.value = value

    class Result:
        def all(self):
            return [Row(date(2026, 8, 1), 28.5), Row(date(2026, 9, 1), 30.3)]

    class Database:
        def execute(self, _statement):
            return Result()

    forwarded = {}

    def analyze(operation, records, **options):
        forwarded["operation"] = operation
        forwarded["records"] = records
        forwarded["options"] = options
        return {"unit": "TWh", "window_months": options["window_months"], "method": "test", "records": []}

    monkeypatch.setattr(routes.analysis_service_client, "analyze", analyze)
    result = routes.get_trend("2026-08", "2026-09", 6, Database())
    assert result["window_months"] == 6
    assert forwarded == {
        "operation": "trend",
        "records": [{"month": "2026-08", "value": 28.5}, {"month": "2026-09", "value": 30.3}],
        "options": {"window_months": 6},
    }

    with pytest.raises(HTTPException) as invalid_month:
        routes.get_summary("2026-13", None, Database())
    assert invalid_month.value.status_code == 422
    with pytest.raises(HTTPException) as invalid_window:
        routes.get_trend(None, None, 1, Database())
    assert invalid_window.value.status_code == 422
