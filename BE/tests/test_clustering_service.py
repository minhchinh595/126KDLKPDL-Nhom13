from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.clustering import kmeans
from scripts.import_electricity_data import load_rows
from service_apps.clustering import main as clustering_app


SECRET = "clustering-test-secret-with-at-least-32-bytes"
HEADERS = {"X-Clustering-Service-Secret": SECRET}


@pytest.fixture
def monthly_records():
    csv_path = Path(__file__).resolve().parents[2] / "data" / "processed" / "vietnam_electricity_demand.csv"
    return [{"month": row["month"].strftime("%Y-%m"), "value": float(row["value"])} for row in load_rows(csv_path)]


def test_clustering_service_health_and_internal_auth(monkeypatch, monthly_records):
    monkeypatch.setenv("CLUSTERING_SERVICE_SECRET", SECRET)
    client = TestClient(clustering_app.app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "success", "service": "clustering"}

    no_secret = client.post("/internal/clustering/run", json={"records": monthly_records})
    assert no_secret.status_code == 401
    wrong_secret = client.post(
        "/internal/clustering/run", json={"records": monthly_records},
        headers={"X-Clustering-Service-Secret": "wrong"},
    )
    assert wrong_secret.status_code == 401


def test_clustering_service_validates_records_and_options(monkeypatch, monthly_records):
    monkeypatch.setenv("CLUSTERING_SERVICE_SECRET", SECRET)
    client = TestClient(clustering_app.app)
    duplicate = [*monthly_records, monthly_records[0]]
    assert client.post("/internal/clustering/train", json={"records": duplicate, "max_k": 5}, headers=HEADERS).status_code == 422
    invalid_demand = [*monthly_records[:-1], {"month": "2026-09", "value": -1}]
    assert client.post("/internal/clustering/run", json={"records": invalid_demand}, headers=HEADERS).status_code == 422
    assert client.post("/internal/clustering/train", json={"records": monthly_records, "max_k": 1}, headers=HEADERS).status_code == 422
    assert client.post("/internal/clustering/run", json={"records": monthly_records, "unexpected": True}, headers=HEADERS).status_code == 422


def test_train_and_run_delegate_to_kmeans_and_run_does_not_train(tmp_path, monkeypatch, monthly_records):
    monkeypatch.setenv("CLUSTERING_SERVICE_SECRET", SECRET)
    artifact = tmp_path / "clustering_test.joblib"
    monkeypatch.setattr(kmeans, "artifact_path", lambda: artifact)
    client = TestClient(clustering_app.app)

    train_calls = []
    real_train = clustering_app.train_and_save_model

    def tracked_train(records, max_k):
        train_calls.append((len(records), max_k))
        return real_train(records, max_k)

    monkeypatch.setattr(clustering_app, "train_and_save_model", tracked_train)
    trained = client.post(
        "/internal/clustering/train",
        json={"records": monthly_records, "max_k": 4},
        headers=HEADERS,
    )
    assert trained.status_code == 200, trained.text
    assert trained.json()["stage"] == "training"
    assert train_calls == [(93, 4)]
    assert artifact.is_file()

    def unexpected_train(*_args, **_kwargs):
        raise AssertionError("run must not train")

    monkeypatch.setattr(clustering_app, "train_and_save_model", unexpected_train)
    run = client.post("/internal/clustering/run", json={"records": monthly_records}, headers=HEADERS)
    assert run.status_code == 200, run.text
    assert run.json()["stage"] == "run"
    assert run.json()["assignments"]
    assert train_calls == [(93, 4)]

    changed_records = [*monthly_records]
    changed_records[-1] = {**changed_records[-1], "value": changed_records[-1]["value"] + 0.1}
    stale = client.post("/internal/clustering/run", json={"records": changed_records}, headers=HEADERS)
    assert stale.status_code == 409
    assert "Admin must train" in stale.json()["detail"]


def test_clustering_service_maps_missing_and_incompatible_artifacts(tmp_path, monkeypatch, monthly_records):
    monkeypatch.setenv("CLUSTERING_SERVICE_SECRET", SECRET)
    monkeypatch.setattr(kmeans, "artifact_path", lambda: tmp_path / "absent.joblib")
    client = TestClient(clustering_app.app)
    missing = client.post("/internal/clustering/run", json={"records": monthly_records}, headers=HEADERS)
    assert missing.status_code == 409
    assert "Admin must train" in missing.json()["detail"]

    def incompatible(_records):
        raise kmeans.ArtifactCompatibilityError("private artifact path must not be returned")

    monkeypatch.setattr(clustering_app, "build_clustering_result", incompatible)
    rejected = client.post("/internal/clustering/run", json={"records": monthly_records}, headers=HEADERS)
    assert rejected.status_code == 409
    assert "private artifact path" not in rejected.json()["detail"]
