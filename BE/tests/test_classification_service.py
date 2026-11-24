import hashlib
from pathlib import Path

import joblib
import pytest
from fastapi.testclient import TestClient

from app.classification import model
from scripts.import_electricity_data import load_rows
from service_apps.classification import main as classification_service


SECRET = "classification-test-secret-with-at-least-32-bytes"
HEADERS = {"X-Classification-Service-Secret": SECRET}


@pytest.fixture
def monthly_records():
    csv_path = Path(__file__).resolve().parents[2] / "data" / "processed" / "vietnam_electricity_demand.csv"
    return [
        {"month": row["month"].strftime("%Y-%m"), "value": float(row["value"])}
        for row in load_rows(csv_path)
    ]


def test_classification_service_health_and_internal_auth(monkeypatch):
    monkeypatch.setenv("CLASSIFICATION_SERVICE_SECRET", SECRET)
    client = TestClient(classification_service.app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "success", "service": "classification"}
    assert client.post("/internal/classification/run", json={"records": []}).status_code == 401
    assert client.post(
        "/internal/classification/run",
        json={"records": []},
        headers={"X-Classification-Service-Secret": "wrong"},
    ).status_code == 401

    monkeypatch.setenv("CLASSIFICATION_SERVICE_SECRET", "")
    unconfigured = client.post(
        "/internal/classification/run",
        json={"records": []},
        headers=HEADERS,
    )
    assert unconfigured.status_code == 503


def test_classification_service_validates_records_and_payload(monkeypatch):
    monkeypatch.setenv("CLASSIFICATION_SERVICE_SECRET", SECRET)
    client = TestClient(classification_service.app)

    invalid_records = [
        [{"month": "2026-13", "value": 1}],
        [{"month": "2026-09", "value": -1}],
        [{"month": "2026-09", "value": "inf"}],
        [{"month": "2026-09", "value": 1}, {"month": "2026-09", "value": 2}],
    ]
    for records in invalid_records:
        response = client.post(
            "/internal/classification/run",
            json={"records": records},
            headers=HEADERS,
        )
        assert response.status_code == 422

    empty_records = client.post(
        "/internal/classification/run",
        json={"records": []},
        headers=HEADERS,
    )
    assert empty_records.status_code == 422

    unexpected = client.post(
        "/internal/classification/run",
        json={"records": [], "unexpected": True},
        headers=HEADERS,
    )
    assert unexpected.status_code == 422


def test_classification_train_delegates_and_run_only_loads_existing_artifact(
    tmp_path,
    monkeypatch,
    monthly_records,
):
    monkeypatch.setenv("CLASSIFICATION_SERVICE_SECRET", SECRET)
    artifact = tmp_path / "classification_test.joblib"
    monkeypatch.setattr(model, "_artifact_path", lambda: artifact)
    training_calls = []
    actual_train = classification_service.train_and_save_model

    def tracked_train(records):
        training_calls.append(len(records))
        return actual_train(records)

    monkeypatch.setattr(classification_service, "train_and_save_model", tracked_train)
    client = TestClient(classification_service.app)
    trained = client.post(
        "/internal/classification/train",
        json={"records": list(reversed(monthly_records))},
        headers=HEADERS,
    )
    assert trained.status_code == 200, trained.text
    assert trained.json()["stage"] == "training"
    assert trained.json()["model_name"] == "RandomForestClassifier"
    assert trained.json()["holdout_metrics"]["confusion_matrix"]["labels"] == [
        "low", "medium", "high"
    ]
    assert training_calls == [len(monthly_records)]
    assert artifact.is_file()
    artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()

    def unexpected_train(*_args, **_kwargs):
        raise AssertionError("Classification Run must not call Train")

    def unexpected_fit(*_args, **_kwargs):
        raise AssertionError("Classification Run must not fit a model")

    monkeypatch.setattr(classification_service, "train_and_save_model", unexpected_train)
    monkeypatch.setattr(model, "_make_model", unexpected_fit)
    forecast = client.post(
        "/internal/classification/run",
        json={"records": monthly_records},
        headers=HEADERS,
    )
    assert forecast.status_code == 200, forecast.text
    assert forecast.json()["stage"] == "forecast"
    assert forecast.json()["forecast_month"] == "2026-10"
    assert forecast.json()["predicted_level"] in {"low", "medium", "high"}
    assert len(forecast.json()["probabilities"]) == 3
    assert training_calls == [len(monthly_records)]
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == artifact_hash


def test_classification_run_handles_missing_and_incompatible_artifacts(
    tmp_path,
    monkeypatch,
    monthly_records,
):
    monkeypatch.setenv("CLASSIFICATION_SERVICE_SECRET", SECRET)
    artifact = tmp_path / "private" / "classification.joblib"
    monkeypatch.setattr(model, "_artifact_path", lambda: artifact)
    client = TestClient(classification_service.app)

    missing = client.post(
        "/internal/classification/run",
        json={"records": monthly_records},
        headers=HEADERS,
    )
    assert missing.status_code == 409
    assert str(tmp_path) not in missing.text

    artifact.parent.mkdir()
    joblib.dump({"not_a_classifier": True}, artifact)
    incompatible = client.post(
        "/internal/classification/run",
        json={"records": monthly_records},
        headers=HEADERS,
    )
    assert incompatible.status_code == 409
    assert str(tmp_path) not in incompatible.text
