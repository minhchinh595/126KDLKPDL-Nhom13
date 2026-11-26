from datetime import datetime, timezone
from types import SimpleNamespace
import platform
import logging

import sklearn
from sqlalchemy.exc import SQLAlchemyError

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies import require_admin, require_analyst
from app.db.database import get_db
from app.main import app
from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE


def model_provenance():
    return {
        "model_type": "prediction", "model_name": "RandomForestRegressor",
        "artifact_name": "electricity_nem_daily_demand_rf_h2.joblib", "artifact_format": "joblib",
        "artifact_version": 2, "contract_version": 2, "horizon_days": 2,
        "feature_schema_version": "nem_daily_demand_h2_v1",
        "python_version": platform.python_version(), "sklearn_version": sklearn.__version__,
        "trained_at": "2026-11-25T00:00:00+00:00",
        "model_parameters": {"n_estimators": 200, "min_samples_leaf": 3},
    }


def payload():
    return {
        "dataset_id": 71,
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
        "data_fingerprint": "a" * 64,
        "as_of_date": "2026-11-26",
        "cutoff_date": "2026-11-25",
        "forecast_date": "2026-11-27",
        "last_observed_date": "2026-11-25",
        "forecast_status": "ready",
        "forecast_message": None,
        "forecast": {"as_of_date": "2026-11-26", "cutoff_date": "2026-11-25", "forecast_date": "2026-11-27"},
    }


class Session:
    def __init__(self):
        self.runs = []

    def add(self, obj):
        self.runs.append(obj)

    def commit(self):
        for run in self.runs:
            if run.id is None:
                run.id = len(self.runs)
            if run.created_at is None:
                run.created_at = datetime.now(timezone.utc)

    def refresh(self, run):
        self.commit()

    def rollback(self):
        pass

    def execute(self, _statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self.runs[-1] if self.runs else None)

    def scalar(self, _statement):
        return len(self.runs)

    def scalars(self, _statement):
        return SimpleNamespace(all=lambda: list(reversed(self.runs)))


def test_prediction_gateway_preserves_routes_rbac_and_provenance(monkeypatch):
    from app.api.routes import prediction

    db = Session()
    data = payload()
    monkeypatch.setattr(prediction, "_load_nem_prediction_payload", lambda _db: data)
    monkeypatch.setattr(prediction.prediction_service_client, "train_nem", lambda _payload: {"stage": "training", "model_name": "RandomForestRegressor", "training_sample_count": 336, "unit": "MW", "model_provenance": model_provenance()})
    monkeypatch.setattr(prediction.prediction_service_client, "run_nem", lambda _payload: {"stage": "forecast", "model_name": "RandomForestRegressor", "forecast_status": "ready", "as_of_date": "2026-11-26", "cutoff_date": "2026-11-25", "forecast_date": "2026-11-27", "horizon_days": 2, "predicted_demand": 18000, "unit": "MW"})

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_admin] = lambda: "admin"
    app.dependency_overrides[require_analyst] = lambda: "analyst"
    try:
        client = TestClient(app)
        trained = client.post("/api/prediction/train")
        assert trained.status_code == 200, trained.text
        assert trained.json()["parameters"]["provenance"]["dataset_id"] == 71
        assert trained.json()["parameters"]["provenance"]["model"] == model_provenance()
        assert trained.json()["metrics"]["stage"] == "training"
        assert "model_provenance" not in trained.json()["metrics"]
        forecast = client.post("/api/prediction/run")
        assert forecast.status_code == 200, forecast.text
        assert forecast.json()["metrics"]["forecast_date"] == "2026-11-27"
        assert client.get("/api/prediction/latest").json()["metrics"]["unit"] == "MW"
        assert client.get("/api/prediction/runs").json()["total"] == 2
        assert client.get("/api/prediction/runs/2").json()["parameters"]["provenance"]["unit"] == "MW"
    finally:
        app.dependency_overrides.clear()


def test_prediction_not_ready_is_not_sent_to_service_or_saved(monkeypatch):
    from app.api.routes import prediction

    db = Session()
    data = payload()
    data.update(forecast_status="not_ready", forecast=None, forecast_message="cutoff missing", last_observed_date="2026-11-24")
    calls = []
    monkeypatch.setattr(prediction, "_load_nem_prediction_payload", lambda _db: data)
    monkeypatch.setattr(prediction.prediction_service_client, "run_nem", lambda _payload: calls.append("called"))

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_admin] = lambda: "admin"
    try:
        response = TestClient(app).post("/api/prediction/run")
        assert response.status_code == 409
        assert response.json()["detail"]["forecast_status"] == "not_ready"
        assert calls == []
        assert db.runs == []
    finally:
        app.dependency_overrides.clear()


def test_prediction_rejected_service_payload_maps_to_422(monkeypatch):
    from app.api.routes import prediction
    from app.clients.prediction import PredictionServiceRejected

    db = Session()
    monkeypatch.setattr(prediction, "_load_nem_prediction_payload", lambda _db: payload())

    def reject(_payload):
        raise PredictionServiceRejected("invalid NEM forecast payload")

    monkeypatch.setattr(prediction.prediction_service_client, "run_nem", reject)
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_admin] = lambda: "admin"
    try:
        response = TestClient(app).post("/api/prediction/run")
        assert response.status_code == 422
        assert response.json()["detail"] == "invalid NEM forecast payload"
    finally:
        app.dependency_overrides.clear()


def test_prediction_gateway_keeps_admin_only_writes_and_analyst_reads():
    def forbidden():
        raise HTTPException(status_code=403, detail="forbidden")

    app.dependency_overrides[require_admin] = forbidden
    app.dependency_overrides[require_analyst] = forbidden
    try:
        client = TestClient(app)
        assert client.post("/api/prediction/train").status_code == 403
        assert client.post("/api/prediction/run").status_code == 403
        assert client.get("/api/prediction/latest").status_code == 403
        assert client.get("/api/prediction/runs").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_prediction_provenance_merge_diagnostic_is_sanitized(caplog):
    from app.api.routes import prediction
    from app.clients.prediction import PredictionServiceUnavailable

    caplog.set_level(logging.WARNING, logger="app.api.routes.prediction")
    metadata = model_provenance()
    metadata["artifact_name"] = "C:/private/path?token=do-not-log"
    response = {"model_provenance": metadata}

    try:
        prediction._nem_training_provenance(
            payload(), response, request_id="gateway-provenance-diagnostic-004",
        )
        raise AssertionError("invalid model provenance must be rejected")
    except PredictionServiceUnavailable:
        pass

    assert "request_id=gateway-provenance-diagnostic-004" in caplog.text
    assert "operation=nem/train" in caplog.text
    assert "stage=provenance_merge" in caplog.text
    assert "exception_class=ModelProvenanceError" in caplog.text
    assert "validation_fields=artifact_name" in caplog.text
    assert "validation_kind=invalid" in caplog.text
    assert "C:/private/path" not in caplog.text
    assert "do-not-log" not in caplog.text


def test_prediction_modelrun_commit_diagnostic_does_not_log_sql_details(caplog):
    from app.api.routes import prediction

    caplog.set_level(logging.ERROR, logger="app.api.routes.prediction")

    class BrokenSession:
        def add(self, _run):
            pass

        def commit(self):
            raise SQLAlchemyError("private SQL parameter do-not-log-sql-value")

    try:
        prediction._save_training_run(
            BrokenSession(),
            result={"model_name": "RandomForestRegressor", "_provenance": {"dataset_id": 71}},
            started_at=datetime.now(timezone.utc),
            request_id="gateway-commit-diagnostic-005",
        )
        raise AssertionError("database commit error must propagate")
    except SQLAlchemyError as exc:
        assert "do-not-log-sql-value" in str(exc)

    assert "request_id=gateway-commit-diagnostic-005" in caplog.text
    assert "operation=nem/train" in caplog.text
    assert "stage=modelrun_commit" in caplog.text
    assert "exception_class=SQLAlchemyError" in caplog.text
    assert "do-not-log-sql-value" not in caplog.text
