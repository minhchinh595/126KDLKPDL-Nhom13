from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
import math
import tempfile
from pathlib import Path
import platform

from fastapi.testclient import TestClient
import pytest
import joblib
import sklearn

from app.clustering import nem_kmeans
from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE
from service_apps.clustering.main import app
from service_apps.clustering.schemas import NEM_FEATURES


SECRET = "nem-clustering-internal-test-secret-at-least-32-bytes"
UNITS = {"demand": "MW", "generation_renewable": "MW", "price": "$/MWh", "renewable_proportion": "%"}


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temporary:
        yield Path(temporary)


def request_payload(count=120, start=date(2026, 1, 1)):
    configurations = {}
    for config_name, names in NEM_FEATURES.items():
        records = []
        for index in range(count):
            phase = index // 30
            features = {
                "demand": 19000 + phase * 1800 + 700 * math.sin(index / 5),
                "generation_renewable": 7200 + (phase % 2) * 1400 + 550 * math.cos(index / 7),
                "price": 45 + phase * 9 + 16 * math.sin(index / 9),
                "renewable_proportion": 38 + phase * 3 + 5 * math.cos(index / 8),
            }
            records.append({
                "date": (start + timedelta(days=index)).isoformat(),
                "features": {name: float(features[name]) for name in names},
            })
        feature_units = {name: UNITS[name] for name in names}
        canonical = {
            "dataset_id": 4,
            "dataset_name": NEM_DATASET_NAME,
            "dataset_source": NEM_DATASET_SOURCE,
            "network_code": "NEM",
            "interval": "1d",
            "feature_names": list(names),
            "feature_units": feature_units,
            "records": records,
        }
        fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        configurations[config_name] = {
            "feature_names": list(names),
            "feature_units": feature_units,
            "records": records,
            "observation_count": len(records),
            "start_date": records[0]["date"],
            "end_date": records[-1]["date"],
            "dropped_date_count": 0,
            "dropped_reasons": {},
            "data_fingerprint": fingerprint,
            "metric_quality": {name: {"unit": UNITS[name], "iqr_outlier_count": 0} for name in names},
        }
    return {
        "dataset_id": 4,
        "dataset_name": NEM_DATASET_NAME,
        "dataset_source": NEM_DATASET_SOURCE,
        "network_code": "NEM",
        "interval": "1d",
        "configurations": configurations,
    }


def recompute_config_fingerprint(payload, config_name):
    config = payload["configurations"][config_name]
    canonical = {
        "dataset_id": payload["dataset_id"],
        "dataset_name": payload["dataset_name"],
        "dataset_source": payload["dataset_source"],
        "network_code": payload["network_code"],
        "interval": payload["interval"],
        "feature_names": config["feature_names"],
        "feature_units": config["feature_units"],
        "records": config["records"],
    }
    config["data_fingerprint"] = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def test_nem_service_evaluates_both_configurations_scalers_and_k_range(tmp_path, monkeypatch):
    monkeypatch.setenv("CLUSTERING_SERVICE_SECRET", SECRET)
    artifact_path = tmp_path / "electricity_nem_daily_kmeans.joblib"
    monkeypatch.setattr(nem_kmeans, "nem_artifact_path", lambda: artifact_path)
    client = TestClient(app)
    payload = request_payload()

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "success", "service": "clustering"}
    no_auth = client.post("/internal/clustering/nem/train", json={**payload, "max_k": 5})
    assert no_auth.status_code == 401

    response = client.post(
        "/internal/clustering/nem/train",
        json={**payload, "max_k": 5},
        headers={"X-Clustering-Service-Secret": SECRET},
    )
    assert response.status_code == 200, response.text
    metrics = response.json()
    assert metrics["stage"] == "training"
    assert len(metrics["candidate_evaluations"]) == 16
    assert {item["feature_set"] for item in metrics["candidate_evaluations"]} == {"A", "B"}
    assert {item["scaler"] for item in metrics["candidate_evaluations"]} == {"standard", "robust"}
    assert {item["k"] for item in metrics["candidate_evaluations"]} == {2, 3, 4, 5}
    assert artifact_path.is_file()
    assert metrics["artifact_name"] == "electricity_nem_daily_kmeans.joblib"
    metadata = metrics["model_provenance"]
    assert metadata["model_type"] == "clustering"
    assert metadata["artifact_name"] == "electricity_nem_daily_kmeans.joblib"
    assert metadata["artifact_format"] == "joblib"
    assert metadata["artifact_version"] == nem_kmeans.NEM_ARTIFACT_VERSION
    assert metadata["contract_version"] == nem_kmeans.NEM_CONTRACT_VERSION
    assert metadata["python_version"] == platform.python_version()
    assert metadata["sklearn_version"] == sklearn.__version__
    assert metadata["trained_at"].endswith("+00:00")
    assert metadata["model_parameters"]["selected_k"] == metrics["selected_k"]
    artifact = joblib.load(artifact_path)
    assert artifact["python_version"] == metadata["python_version"]
    assert artifact["sklearn_version"] == metadata["sklearn_version"]
    assert "secret" not in str(metadata).lower()
    assert metrics["cluster_label_semantics"].startswith("Groups of days")
    assert all(
        math.isfinite(value)
        for centroid in metrics["centroids_original_units"]
        for value in centroid.values()
    )


def test_run_loads_artifact_without_fit_and_allows_new_dates_without_retraining(tmp_path, monkeypatch):
    monkeypatch.setenv("CLUSTERING_SERVICE_SECRET", SECRET)
    artifact_path = tmp_path / "electricity_nem_daily_kmeans.joblib"
    monkeypatch.setattr(nem_kmeans, "nem_artifact_path", lambda: artifact_path)
    client = TestClient(app)
    training_payload = request_payload()
    trained = client.post(
        "/internal/clustering/nem/train",
        json={**training_payload, "max_k": 5},
        headers={"X-Clustering-Service-Secret": SECRET},
    )
    assert trained.status_code == 200, trained.text
    before = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

    def forbidden_fit(*_args, **_kwargs):
        raise AssertionError("Run must never fit a model")

    monkeypatch.setattr(nem_kmeans.KMeans, "fit", forbidden_fit)
    monkeypatch.setattr(nem_kmeans.KMeans, "fit_predict", forbidden_fit)
    updated_payload = request_payload(count=121)
    selected_features = trained.json()["feature_names"]
    for record in updated_payload["configurations"][trained.json()["feature_set"]]["records"][-1:]:
        for name in selected_features:
            record["features"][name] *= 4
    config_name = trained.json()["feature_set"]
    selected = updated_payload["configurations"][config_name]
    selected["observation_count"] = len(selected["records"])
    selected["end_date"] = selected["records"][-1]["date"]
    recompute_config_fingerprint(updated_payload, config_name)

    response = client.post(
        "/internal/clustering/nem/run",
        json=updated_payload,
        headers={"X-Clustering-Service-Secret": SECRET},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["stage"] == "run"
    assert result["training_data_fingerprint"] != result["run_data_fingerprint"]
    assert result["run_observation_count"] == 121
    assert result["drift_warning"] is True
    assert len(result["assignments"]) == 121
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == before


def test_run_rejects_unit_mismatch_without_touching_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("CLUSTERING_SERVICE_SECRET", SECRET)
    artifact_path = tmp_path / "electricity_nem_daily_kmeans.joblib"
    monkeypatch.setattr(nem_kmeans, "nem_artifact_path", lambda: artifact_path)
    client = TestClient(app)
    payload = request_payload()
    response = client.post(
        "/internal/clustering/nem/train",
        json={**payload, "max_k": 5},
        headers={"X-Clustering-Service-Secret": SECRET},
    )
    assert response.status_code == 200, response.text
    before = artifact_path.read_bytes()
    run_payload = deepcopy(payload)
    selected_set = response.json()["feature_set"]
    feature = run_payload["configurations"][selected_set]["feature_names"][0]
    run_payload["configurations"][selected_set]["feature_units"][feature] = "wrong-unit"
    recompute_config_fingerprint(run_payload, selected_set)
    rejected = client.post(
        "/internal/clustering/nem/run",
        json=run_payload,
        headers={"X-Clustering-Service-Secret": SECRET},
    )
    assert rejected.status_code == 409
    assert "feature units" in rejected.json()["detail"]
    assert artifact_path.read_bytes() == before


def test_nem_service_rejects_invalid_order_values_and_dataset_identity(monkeypatch):
    monkeypatch.setenv("CLUSTERING_SERVICE_SECRET", SECRET)
    client = TestClient(app)
    payload = request_payload(count=3)
    payload["configurations"]["A"]["records"][1]["features"]["demand"] = "NaN"
    response = client.post(
        "/internal/clustering/nem/train",
        json={**payload, "max_k": 2},
        headers={"X-Clustering-Service-Secret": SECRET},
    )
    assert response.status_code == 422

    payload = request_payload(count=3)
    payload["dataset_source"] = "https://not-the-configured-source"
    response = client.post(
        "/internal/clustering/nem/train",
        json={**payload, "max_k": 2},
        headers={"X-Clustering-Service-Secret": SECRET},
    )
    assert response.status_code == 422
