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
        "model_type": "classification", "model_name": "RandomForestClassifier",
        "artifact_name": "electricity_nem_daily_demand_classifier_h2.joblib", "artifact_format": "joblib",
        "artifact_version": 2, "contract_version": 2, "horizon_days": 2,
        "feature_schema_version": "nem_daily_demand_h2_v1",
        "python_version": platform.python_version(), "sklearn_version": sklearn.__version__,
        "trained_at": "2026-11-25T00:00:00+00:00",
        "model_parameters": {"n_estimators": 200, "min_samples_leaf": 3},
    }


def service_payload():
    return {
        "dataset_id": 83,
        "dataset_name": NEM_DATASET_NAME,
        "dataset_source": NEM_DATASET_SOURCE,
        "network_code": "NEM",
        "metric": "demand",
        "interval": "1d",
        "unit": "MW",
        "horizon_days": 2,
        "feature_schema_version": "nem_daily_demand_h2_v1",
        "feature_names": ["demand_at_cutoff", "demand_6d_before_cutoff", "demand_13d_before_cutoff", "demand_27d_before_cutoff", "day_of_week", "day_of_year"],
        "feature_units": {"demand_at_cutoff": "MW", "demand_6d_before_cutoff": "MW", "demand_13d_before_cutoff": "MW", "demand_27d_before_cutoff": "MW", "day_of_week": "weekday_index", "day_of_year": "day_of_year_index"},
        "observation_start": "2025-11-25",
        "observation_end": "2026-11-25",
        "observation_count": 365,
        "training_start": "2025-12-23",
        "training_end": "2026-11-24",
        "training_sample_count": 336,
        "excluded_sample_count": 29,
        "exclusion_reasons": {"missing_lag_observation": 29},
        "missing_dates": [],
        "data_fingerprint": "b" * 64,
        "as_of_date": "2026-11-26",
        "cutoff_date": "2026-11-25",
        "forecast_date": "2026-11-27",
        "last_observed_date": "2026-11-25",
        "forecast_status": "ready",
        "forecast_message": None,
        "forecast": {"as_of_date": "2026-11-26", "cutoff_date": "2026-11-25", "forecast_date": "2026-11-27"},
    }


class FakeSession:
    def __init__(self):
        self.rows = []

    def add(self, row):
        self.rows.append(row)

    def commit(self):
        for row in self.rows:
            if row.id is None:
                row.id = len(self.rows)
            if row.created_at is None:
                row.created_at = datetime.now(timezone.utc)

    def refresh(self, row):
        self.commit()

    def rollback(self):
        return None

    def execute(self, _statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self.rows[-1] if self.rows else None)

    def scalar(self, _statement):
        return len(self.rows)

    def scalars(self, _statement):
        return SimpleNamespace(all=lambda: list(reversed(self.rows)))


def test_gateway_uses_nem_client_and_saves_dataset_provenance(monkeypatch):
    from app.api.routes import classification

    session = FakeSession()
    payload = service_payload()
    calls = []
    monkeypatch.setattr(classification, "_load_nem_classification_payload", lambda _db: payload)
    monkeypatch.setattr(classification, "_load_demand_records", lambda _db: (_ for _ in ()).throw(AssertionError("VNM loader must not be used")))

    def train_nem(body):
        calls.append(("train", body["dataset_source"], body["unit"]))
        return {"stage": "training", "model_name": "RandomForestClassifier", "threshold_mw": 17000, "training_sample_count": 336, "model_provenance": model_provenance()}

    def run_nem(body):
        calls.append(("run", body["network_code"], body["interval"]))
        return {"stage": "forecast", "model_name": "RandomForestClassifier", "forecast_status": "ready", "as_of_date": "2026-11-26", "cutoff_date": "2026-11-25", "forecast_date": "2026-11-27", "horizon_days": 2, "predicted_level": "High", "threshold_mw": 17000, "unit": "MW"}

    monkeypatch.setattr(classification.classification_service_client, "train_nem", train_nem)
    monkeypatch.setattr(classification.classification_service_client, "run_nem", run_nem)

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_admin] = lambda: "admin"
    app.dependency_overrides[require_analyst] = lambda: "analyst"
    try:
        client = TestClient(app)
        trained = client.post("/api/classification/train")
        assert trained.status_code == 200, trained.text
        assert trained.json()["parameters"]["provenance"]["dataset_id"] == 83
        assert trained.json()["parameters"]["provenance"]["unit"] == "MW"
        assert trained.json()["parameters"]["provenance"]["model"] == model_provenance()
        assert trained.json()["metrics"]["stage"] == "training"
        assert "model_provenance" not in trained.json()["metrics"]
        forecast = client.post("/api/classification/run")
        assert forecast.status_code == 200, forecast.text
        assert forecast.json()["metrics"]["forecast_date"] == "2026-11-27"
        assert client.get("/api/classification/latest").json()["metrics"]["predicted_level"] == "High"
        assert client.get("/api/classification/runs").json()["total"] == 2
        assert client.get("/api/classification/runs/2").json()["parameters"]["provenance"]["dataset_source"] == NEM_DATASET_SOURCE
        assert calls == [("train", NEM_DATASET_SOURCE, "MW"), ("run", "NEM", "1d")]
    finally:
        app.dependency_overrides.clear()


def test_classification_not_ready_is_not_sent_to_service_or_saved(monkeypatch):
    from app.api.routes import classification

    session = FakeSession()
    payload = service_payload()
    payload.update(forecast_status="not_ready", forecast=None, forecast_message="cutoff missing", last_observed_date="2026-11-24")
    calls = []
    monkeypatch.setattr(classification, "_load_nem_classification_payload", lambda _db: payload)
    monkeypatch.setattr(classification.classification_service_client, "run_nem", lambda _body: calls.append("called"))

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_admin] = lambda: "admin"
    try:
        response = TestClient(app).post("/api/classification/run")
        assert response.status_code == 409
        assert response.json()["detail"]["forecast_status"] == "not_ready"
        assert calls == []
        assert session.rows == []
    finally:
        app.dependency_overrides.clear()


def test_classification_rejected_service_payload_maps_to_422(monkeypatch):
    from app.api.routes import classification
    from app.clients.classification import ClassificationServiceRejected

    session = FakeSession()
    monkeypatch.setattr(classification, "_load_nem_classification_payload", lambda _db: service_payload())

    def reject(_payload):
        raise ClassificationServiceRejected("invalid NEM classification payload")

    monkeypatch.setattr(classification.classification_service_client, "run_nem", reject)
    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_admin] = lambda: "admin"
    try:
        response = TestClient(app).post("/api/classification/run")
        assert response.status_code == 422
        assert response.json()["detail"] == "invalid NEM classification payload"
    finally:
        app.dependency_overrides.clear()


def test_gateway_preserves_admin_write_and_analyst_read_rbac():
    def forbidden():
        raise HTTPException(status_code=403, detail="forbidden")

    app.dependency_overrides[require_admin] = forbidden
    app.dependency_overrides[require_analyst] = forbidden
    try:
        client = TestClient(app)
        assert client.post("/api/classification/train").status_code == 403
        assert client.post("/api/classification/run").status_code == 403
        assert client.get("/api/classification/latest").status_code == 403
        assert client.get("/api/classification/runs").status_code == 403
    finally:
        app.dependency_overrides.clear()
