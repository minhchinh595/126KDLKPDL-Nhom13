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
        "/api/analysis/summary": {"start_at", "end_at"},
        "/api/analysis/trend": {"start_at", "end_at", "view", "metric"},
        "/api/analysis/seasonality": {"start_at", "end_at"},
        "/api/analysis/correlation": {"start_at", "end_at"},
        "/api/analysis/distribution": {"start_at", "end_at", "metric", "interval", "bins"},
        "/api/analysis/scatter": {"start_at", "end_at", "x_metric", "y_metric"},
    }
    for path, expected_parameters in expected.items():
        operation = schema["paths"][path]["get"]
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


def test_gateway_client_routes_nem_operations_to_internal_nem_namespace():
    captured = {}

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return b'{"metric":"demand","view":"week"}'

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return Response()

    client = AnalysisServiceClient(base_url="http://analysis.internal:8101", secret="analysis-test-secret-with-at-least-32-bytes", opener=opener)
    result = client.analyze("nem-trend", [], view="week", metric="demand")
    assert captured["url"] == "http://analysis.internal:8101/internal/analysis/nem/trend"
    assert result["view"] == "week"


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
    from datetime import datetime, timezone

    class Row:
        metric = "demand"
        interval = "1d"
        observed_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
        value = 28.5
        unit = "MW"
        result = "NEM"
        grouping_type = "network"
        grouping_code = ""

    class Dataset:
        name = "Open Electricity NEM"

    class Database:
        pass

    forwarded = {}

    def analyze(operation, records, **options):
        forwarded["operation"] = operation
        forwarded["records"] = records
        forwarded["options"] = options
        return {"metric": "demand", "unit": "MW", "view": options["view"], "records": []}

    monkeypatch.setattr(routes.analysis_service_client, "analyze", analyze)
    monkeypatch.setattr(routes, "query_observations", lambda *_args, **_kwargs: (Dataset(), [Row()], 1))
    result = routes.get_trend(start_at=datetime(2026, 8, 1, tzinfo=timezone.utc), end_at=datetime(2026, 9, 1, tzinfo=timezone.utc), metric="demand", view="month", db=Database())
    assert result["view"] == "month"
    assert forwarded == {
        "operation": "nem-trend",
        "records": [{"metric": "demand", "interval": "1d", "observed_at": Row.observed_at.isoformat(), "value": 28.5, "unit": "MW", "result": "NEM", "grouping_type": "network", "grouping_code": ""}] * 5,
        "options": {"view": "month", "metric": "demand"},
    }
