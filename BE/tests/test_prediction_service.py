from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.prediction import model
from scripts.import_electricity_data import load_rows
from service_apps.prediction import main as prediction_service


SECRET = "prediction-test-secret-with-at-least-32-bytes"
HEADERS = {"X-Prediction-Service-Secret": SECRET}


@pytest.fixture
def monthly_records():
    csv_path = Path(__file__).resolve().parents[2] / "data" / "processed" / "vietnam_electricity_demand.csv"
    return [
        {"month": row["month"].strftime("%Y-%m"), "value": float(row["value"])}
        for row in load_rows(csv_path)
    ]


def test_prediction_service_health_and_internal_auth(monkeypatch):
    monkeypatch.setenv("PREDICTION_SERVICE_SECRET", SECRET)
    client = TestClient(prediction_service.app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "success", "service": "prediction"}
    assert client.post("/internal/prediction/run", json={"records": []}).status_code == 401
    assert client.post(
        "/internal/prediction/run",
        json={"records": []},
        headers={"X-Prediction-Service-Secret": "wrong"},
    ).status_code == 401


def test_prediction_service_validates_records_and_payload(monkeypatch):
    monkeypatch.setenv("PREDICTION_SERVICE_SECRET", SECRET)
    client = TestClient(prediction_service.app)

    assert client.post(
        "/internal/prediction/train",
        json={"records": [{"month": "2026-13", "value": 1}]},
        headers=HEADERS,
    ).status_code == 422
    assert client.post(
        "/internal/prediction/run",
        json={"records": [{"month": "2026-09", "value": -1}]},
        headers=HEADERS,
    ).status_code == 422
    assert client.post(
        "/internal/prediction/run",
        json={"records": [{"month": "2026-09", "value": float("inf").__str__()}]},
        headers=HEADERS,
    ).status_code == 422
    assert client.post(
        "/internal/prediction/run",
        json={"records": [{"month": "2026-09", "value": 1}, {"month": "2026-09", "value": 2}]},
        headers=HEADERS,
    ).status_code == 422
    assert client.post(
        "/internal/prediction/run",
        json={"records": [], "unexpected": True},
        headers=HEADERS,
    ).status_code == 422


def test_prediction_train_delegates_to_model_and_run_does_not_refit(
    tmp_path,
    monkeypatch,
    monthly_records,
):
    monkeypatch.setenv("PREDICTION_SERVICE_SECRET", SECRET)
    artifact = tmp_path / "prediction_test.joblib"
    monkeypatch.setattr(model, "_artifact_path", lambda: artifact)
    calls = []
    actual_train = prediction_service.train_and_save_model

    def tracked_train(records):
        calls.append(len(records))
        return actual_train(records)

    monkeypatch.setattr(prediction_service, "train_and_save_model", tracked_train)
    client = TestClient(prediction_service.app)
    trained = client.post(
        "/internal/prediction/train",
        json={"records": list(reversed(monthly_records))},
        headers=HEADERS,
    )
    assert trained.status_code == 200, trained.text
    assert trained.json()["stage"] == "training"
    assert trained.json()["model_name"] == "RandomForestRegressor"
    assert calls == [len(monthly_records)]
    assert artifact.is_file()

    def unexpected_train(*_args, **_kwargs):
        raise AssertionError("run must not train")

    def unexpected_fit(*_args, **_kwargs):
        raise AssertionError("run must not fit a model")

    monkeypatch.setattr(prediction_service, "train_and_save_model", unexpected_train)
    monkeypatch.setattr(model, "_make_model", unexpected_fit)
    forecast = client.post(
        "/internal/prediction/run",
        json={"records": monthly_records},
        headers=HEADERS,
    )
    assert forecast.status_code == 200, forecast.text
    assert forecast.json()["stage"] == "forecast"
    assert forecast.json()["forecast_month"] == "2026-10"
    assert calls == [len(monthly_records)]


def test_prediction_run_maps_missing_and_incompatible_artifacts_without_path_leak(
    tmp_path,
    monkeypatch,
    monthly_records,
):
    monkeypatch.setenv("PREDICTION_SERVICE_SECRET", SECRET)
    absent_path = tmp_path / "private" / "missing.joblib"
    monkeypatch.setattr(model, "_artifact_path", lambda: absent_path)
    client = TestClient(prediction_service.app)

    missing = client.post(
        "/internal/prediction/run",
        json={"records": monthly_records},
        headers=HEADERS,
    )
    assert missing.status_code == 409
    assert str(tmp_path) not in missing.text

    def incompatible(_records):
        raise ValueError("Prediction model artifact is incomplete or incompatible: " + str(absent_path))

    monkeypatch.setattr(prediction_service, "forecast_next_month", incompatible)
    response = client.post(
        "/internal/prediction/run",
        json={"records": monthly_records},
        headers=HEADERS,
    )
    assert response.status_code == 409
    assert str(tmp_path) not in response.text
