from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.analysis.nem import correlation, distribution, scatter, seasonality, summary, trend
from service_apps.analysis.main import app
from service_apps.analysis.nem_schemas import NEMRecord


def records():
    rows = []
    values = {
        "demand": ("MW", [100, 110, 120]),
        "price": ("$/MWh", [-5, 20, 30]),
        "demand_energy": ("MWh", [2400, 2500, 2600]),
        "generation_renewable": ("MW", [40, 50, 60]),
        "renewable_proportion": ("%", [40, 45, 50]),
    }
    for metric, (unit, values_for_metric) in values.items():
        for day, value in zip(("2026-01-01", "2026-01-02", "2026-01-04"), values_for_metric):
            rows.append({"metric": metric, "interval": "1d", "observed_at": f"{day}T00:00:00+10:00", "value": value, "unit": unit, "result": "NEM", "grouping_type": "network", "grouping_code": ""})
    return rows


def test_nem_summary_weekday_seasonality_and_trend_preserve_gap():
    data = records()
    assert summary(data)["sample_count"] == 3
    weekly = trend(data, "day")["records"]
    assert [row["period"] for row in weekly] == ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]
    assert weekly[2]["value"] is None and weekly[2]["sample_count"] == 0
    assert seasonality(data)["limitation"].startswith("Only about one year")


def test_nem_correlation_aligns_local_dates_and_scatter_pairs_in_backend():
    data = records()
    result = correlation(data)
    assert result["sample_dates"] == 3
    assert result["pair_counts"]["demand"]["price"] == 3
    points = scatter(data, "demand", "price")["points"]
    assert len(points) == 3 and points[0]["x"] == 100


def test_nem_distribution_keeps_metric_unit_and_negative_price():
    result = distribution(records(), "price", "1d", 4)
    assert result["unit"] == "$/MWh"
    assert result["sample_count"] == 3
    assert sum(bucket["count"] for bucket in result["bins"]) == 3
    assert result["bins"][0]["start"] == -5


def test_trend_uses_metric_appropriate_resampling_and_discloses_limits():
    data = records()
    energy = trend(data, "week", "demand_energy")
    assert energy["unit"] == "MWh"
    assert energy["records"][0]["value"] == 7500
    monthly_energy = trend(data, "month", "demand_energy")
    assert monthly_energy["records"][0]["value"] == 7500
    assert monthly_energy["records"][0]["expected_days"] == 4
    weighted_price = trend(data, "week", "price")
    assert weighted_price["records"][0]["value"] == pytest.approx((-5*2400 + 20*2500 + 30*2600) / 7500)
    assert weighted_price["records"][0]["weighted_sample_count"] == 3
    proportion = trend(data, "month", "renewable_proportion")
    assert proportion["records"][0]["value"] is None
    assert "requires" in proportion["aggregation"]


def test_nem_analysis_internal_endpoint_requires_secret_and_runs_statelessly(monkeypatch):
    secret = "nem-analysis-test-secret-at-least-32-bytes"
    monkeypatch.setenv("ANALYSIS_SERVICE_SECRET", secret)
    client = TestClient(app)
    payload = {"records": records()}
    assert client.post("/internal/analysis/nem/correlation", json=payload).status_code == 401
    response = client.post("/internal/analysis/nem/correlation", json=payload, headers={"X-Analysis-Service-Secret": secret})
    assert response.status_code == 200, response.text
    assert response.json()["sample_dates"] == 3


def test_nem_analytics_rejects_naive_timestamp():
    row = records()[0] | {"observed_at": "2026-01-01T00:00:00"}
    with pytest.raises(ValueError, match="timezone"):
        summary([row])


def test_internal_nem_schema_rejects_naive_time_and_unsupported_metric_interval():
    row = records()[0]
    with pytest.raises(ValueError, match="timezone"):
        NEMRecord(**(row | {"observed_at": "2026-01-01T00:00:00"}))
    with pytest.raises(ValueError, match="metric and interval"):
        NEMRecord(**(row | {"metric": "price", "interval": "5m"}))
