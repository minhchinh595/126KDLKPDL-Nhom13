from datetime import datetime, timezone
from types import SimpleNamespace
import platform

import sklearn

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies import require_admin, require_analyst
from app.db.database import get_db
from app.main import app
from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE


def model_provenance():
    return {
        "model_type": "clustering", "model_name": "KMeans",
        "artifact_name": "electricity_nem_daily_kmeans.joblib", "artifact_format": "joblib",
        "artifact_version": 1, "contract_version": 1,
        "python_version": platform.python_version(), "sklearn_version": sklearn.__version__,
        "trained_at": "2026-11-25T00:00:00+00:00",
        "model_parameters": {"selected_k": 3, "scaler": "standard"},
    }


def payload():
    names_a = ["demand", "generation_renewable", "price"]
    names_b = [*names_a, "renewable_proportion"]
    configs = {}
    units = {"demand": "MW", "generation_renewable": "MW", "price": "$/MWh", "renewable_proportion": "%"}
    for key, names in (("A", names_a), ("B", names_b)):
        configs[key] = {
            "feature_names": names,
            "feature_units": {name: units[name] for name in names},
            "start_date": "2026-01-01",
            "end_date": "2026-11-24",
            "observation_count": 365,
            "data_fingerprint": f"fingerprint-{key}",
            "dropped_date_count": 0,
            "dropped_reasons": {},
            "metric_quality": {name: {"unit": units[name], "iqr_outlier_count": 0} for name in names},
        }
    return {
        "dataset_id": 4,
        "dataset_name": NEM_DATASET_NAME,
        "dataset_source": NEM_DATASET_SOURCE,
        "network_code": "NEM",
        "interval": "1d",
        "configurations": configs,
    }


class FakeSession:
    def __init__(self):
        self.items = []

    def add(self, item):
        self.items.append(item)

    def _refresh_fields(self, item):
        if item.id is None:
            item.id = self.items.index(item) + 1
        item.created_at = item.created_at or datetime.now(timezone.utc)

    def flush(self):
        self._refresh_fields(self.items[-1])

    def commit(self):
        for item in self.items:
            self._refresh_fields(item)

    def refresh(self, item):
        self._refresh_fields(item)

    def rollback(self):
        return None

    def execute(self, _statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self.items[-1] if self.items else None)

    def scalar(self, _statement):
        return len(self.items)

    def scalars(self, _statement):
        return SimpleNamespace(all=lambda: list(reversed(self.items)))


def test_public_gateway_train_run_history_and_jsonb_provenance(monkeypatch):
    from app.api.routes import clustering

    session = FakeSession()
    incoming = payload()
    monkeypatch.setattr(clustering, "_load_nem_clustering_payload", lambda _db: incoming)
    monkeypatch.setattr(
        clustering.clustering_service_client,
        "train_nem",
        lambda _payload, max_k=5: {"stage": "training", "selected_k": 3, "model_provenance": model_provenance()},
    )
    monkeypatch.setattr(
        clustering.clustering_service_client,
        "run_nem",
        lambda _payload: {"stage": "run", "run_data_fingerprint": "fingerprint-A"},
    )

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_admin] = lambda: "admin"
    app.dependency_overrides[require_analyst] = lambda: "analyst"
    try:
        client = TestClient(app)
        trained = client.post("/api/clustering/train?max_k=5")
        assert trained.status_code == 200, trained.text
        assert trained.json()["metrics"]["stage"] == "training"
        provenance = trained.json()["parameters"]["provenance"]
        assert provenance["dataset_id"] == 4
        assert provenance["feature_configurations"]["A"]["feature_units"]["price"] == "$/MWh"
        assert provenance["model"] == model_provenance()
        assert trained.json()["metrics"]["stage"] == "training"
        assert "model_provenance" not in trained.json()["metrics"]

        ran = client.post("/api/clustering/run")
        assert ran.status_code == 200, ran.text
        assert ran.json()["parameters"]["stage"] == "run"
        assert ran.json()["metrics"]["stage"] == "run"
        assert client.get("/api/clustering/latest").json()["metrics"]["stage"] == "run"
        history = client.get("/api/clustering/runs")
        assert history.status_code == 200
        assert history.json()["total"] == 2
        assert client.get("/api/clustering/runs/2").json()["parameters"]["provenance"]["dataset_source"] == NEM_DATASET_SOURCE
    finally:
        app.dependency_overrides.clear()


def test_public_gateway_keeps_admin_write_and_analyst_read_permissions():
    def forbidden_admin():
        raise HTTPException(status_code=403, detail="admin required")

    def forbidden_analyst():
        raise HTTPException(status_code=403, detail="analyst required")

    app.dependency_overrides[require_admin] = forbidden_admin
    app.dependency_overrides[require_analyst] = forbidden_analyst
    try:
        client = TestClient(app)
        assert client.post("/api/clustering/train").status_code == 403
        assert client.post("/api/clustering/run").status_code == 403
        assert client.get("/api/clustering/latest").status_code == 403
        assert client.get("/api/clustering/runs").status_code == 403
    finally:
        app.dependency_overrides.clear()
