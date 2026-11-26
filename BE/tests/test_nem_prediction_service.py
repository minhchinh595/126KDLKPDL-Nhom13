from datetime import date, datetime, timedelta
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import platform
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pytest
import joblib
import sklearn
from fastapi.testclient import TestClient

from app.prediction import nem_model
from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE
from app.services.nem_ml_data import DailyObservation, NEMDailyMLData, build_nem_prediction_payload
from service_apps.prediction.main import app


SECRET = "nem-prediction-service-test-secret-at-least-32-bytes"
HEADERS = {"X-Prediction-Service-Secret": SECRET}
BRISBANE = ZoneInfo("Australia/Brisbane")


def make_payload(days: int = 365, *, now: datetime | None = None) -> dict:
    end = date(2026, 11, 25) + timedelta(days=days - 365)
    now = now or datetime(2026, 11, 26, 12, tzinfo=BRISBANE)
    start = end - timedelta(days=days - 1)
    observations = tuple(
        DailyObservation(
            observed_at=datetime.combine(start + timedelta(days=index), datetime.min.time(), tzinfo=BRISBANE),
            value=Decimal(str(15000 + index * 3 + (index % 7) * 90)),
            unit="MW",
            result="Demand",
        )
        for index in range(days)
    )
    data = NEMDailyMLData(
        dataset_id=71,
        dataset_name=NEM_DATASET_NAME,
        dataset_source=NEM_DATASET_SOURCE,
        network_code="NEM",
        metric="demand",
        interval="1d",
        unit="MW",
        observations=observations,
        start_date=start,
        end_date=end,
        missing_dates=(),
        duplicate_timestamps=(),
        duplicate_local_dates=(),
        unit_mismatch_count=0,
        null_timestamp_count=0,
        timezone_naive_count=0,
        null_value_count=0,
        invalid_value_count=0,
        non_finite_value_count=0,
        zero_count=0,
        negative_count=0,
        data_fingerprint="",
    )
    # The production loader computes this fingerprint; use its canonical helper
    # through the same payload structure by rebuilding the data fingerprint.
    from app.services.nem_ml_data import _fingerprint
    fingerprint = _fingerprint(
        dataset_id=data.dataset_id,
        dataset_name=data.dataset_name,
        dataset_source=data.dataset_source,
        network_code=data.network_code,
        metric=data.metric,
        interval=data.interval,
        unit=data.unit,
        rows=data.observations,
    )
    return build_nem_prediction_payload(replace(data, data_fingerprint=fingerprint), now=now)


@pytest.fixture
def artifact_dir():
    with TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
        yield Path(temp)


def test_nem_prediction_train_artifact_and_run_without_refit(monkeypatch, artifact_dir):
    monkeypatch.setenv("PREDICTION_SERVICE_SECRET", SECRET)
    h2_path = artifact_dir / "nem-model-h2.joblib"
    monkeypatch.setattr(nem_model, "nem_h2_artifact_path", lambda: h2_path)
    monkeypatch.setattr(nem_model, "nem_artifact_path", lambda: artifact_dir / "nem-model-h1.joblib")
    client = TestClient(app)
    payload = make_payload()

    unauthorized = client.post("/internal/prediction/nem/train", json=payload)
    assert unauthorized.status_code == 401
    trained = client.post("/internal/prediction/nem/train", json=payload, headers=HEADERS)
    assert trained.status_code == 200, trained.text
    training_result = trained.json()
    assert training_result["stage"] == "training"
    assert training_result["unit"] == "MW"
    assert training_result["metric"] == "demand"
    assert training_result["observation_start"] == payload["observation_start"]
    assert training_result["observation_end"] == payload["observation_end"]
    assert training_result["training_sample_count"] == 336
    assert training_result["forecast_horizon_days"] == 2
    assert training_result["feature_schema_version"] == "nem_daily_demand_h2_v1"
    assert training_result["validation"]["shuffle"] is False
    assert training_result["validation"]["fold_count"] == 4
    for fold in training_result["validation"]["folds"]:
        assert date.fromisoformat(fold["training_end"]) + timedelta(days=2) <= date.fromisoformat(fold["validation_start"])
    assert training_result["validation"]["lowest_mae_method"] in {
        "random_forest", "persistence_baseline", "seasonal_naive_7d_baseline"
    }
    metadata = training_result["model_provenance"]
    assert metadata["model_type"] == "prediction"
    assert metadata["artifact_name"] == "nem-model-h2.joblib"
    assert metadata["artifact_format"] == "joblib"
    assert metadata["artifact_version"] == nem_model.ARTIFACT_VERSION
    assert metadata["contract_version"] == nem_model.CONTRACT_VERSION
    assert metadata["python_version"] == platform.python_version()
    assert metadata["sklearn_version"] == sklearn.__version__
    assert metadata["trained_at"].endswith("+00:00")
    assert metadata["model_parameters"] == nem_model.MODEL_PARAMETERS
    assert "secret" not in str(metadata).lower()
    assert (artifact_dir / "nem-model-h2.joblib").is_file()
    artifact = joblib.load(artifact_dir / "nem-model-h2.joblib")
    assert artifact["trained_at"] == metadata["trained_at"]

    def forbidden_fit():
        raise AssertionError("run must not train or fit")

    monkeypatch.setattr(nem_model, "_new_model", forbidden_fit)
    # Inference loads the separately configured H2 artifact path.
    monkeypatch.setattr(nem_model, "nem_h2_artifact_path", lambda: h2_path)
    ran = client.post("/internal/prediction/nem/run", json=payload, headers=HEADERS)
    assert ran.status_code == 200, ran.text
    result = ran.json()
    assert result["forecast_date"] == "2026-11-27"
    assert result["cutoff_date"] == "2026-11-25"
    assert result["horizon_days"] == 2
    assert result["forecast_status"] == "ready"
    assert result["unit"] == "MW"
    assert result["training_data_fingerprint"] == result["run_data_fingerprint"]
    assert result["dataset_provenance"] == {
        "dataset_id": payload["dataset_id"],
        "dataset_name": payload["dataset_name"],
        "dataset_source": payload["dataset_source"],
        "network_code": payload["network_code"],
        "metric": payload["metric"],
        "interval": payload["interval"],
        "unit": payload["unit"],
    }

    newer_payload = make_payload(367, now=datetime(2026, 11, 27, 12, tzinfo=BRISBANE))
    newer = client.post("/internal/prediction/nem/run", json=newer_payload, headers=HEADERS)
    assert newer.status_code == 200, newer.text
    assert newer.json()["forecast_date"] == "2026-11-28"
    assert newer.json()["training_data_fingerprint"] != newer.json()["run_data_fingerprint"]


def test_nem_prediction_rejects_unit_schema_and_dataset_mismatch(monkeypatch, artifact_dir):
    monkeypatch.setenv("PREDICTION_SERVICE_SECRET", SECRET)
    h2_path = artifact_dir / "nem-model-h2.joblib"
    monkeypatch.setattr(nem_model, "nem_h2_artifact_path", lambda: h2_path)
    monkeypatch.setattr(nem_model, "nem_artifact_path", lambda: artifact_dir / "nem-model-h1.joblib")
    payload = make_payload()
    client = TestClient(app)
    assert client.post("/internal/prediction/nem/train", json=payload, headers=HEADERS).status_code == 200
    monkeypatch.setattr(nem_model, "nem_h2_artifact_path", lambda: h2_path)

    wrong_unit = {**payload, "unit": "MWh"}
    assert client.post("/internal/prediction/nem/run", json=wrong_unit, headers=HEADERS).status_code == 422
    wrong_features = {**payload, "feature_names": ["demand_at_cutoff"]}
    assert client.post("/internal/prediction/nem/run", json=wrong_features, headers=HEADERS).status_code == 422
    wrong_dataset = {**payload, "dataset_id": payload["dataset_id"] + 1}
    assert client.post("/internal/prediction/nem/run", json=wrong_dataset, headers=HEADERS).status_code == 409


def test_nem_prediction_run_requires_a_trained_artifact(monkeypatch, artifact_dir):
    monkeypatch.setenv("PREDICTION_SERVICE_SECRET", SECRET)
    monkeypatch.setattr(nem_model, "nem_h2_artifact_path", lambda: artifact_dir / "absent-h2.joblib")
    legacy_path = artifact_dir / "available-h1.joblib"
    joblib.dump({"artifact_version": 1}, legacy_path)
    monkeypatch.setattr(nem_model, "nem_artifact_path", lambda: legacy_path)
    response = TestClient(app).post(
        "/internal/prediction/nem/run",
        json=make_payload(),
        headers=HEADERS,
    )
    assert response.status_code == 409
    assert "artifact is missing" in response.text
    assert "not_ready" not in response.text
    assert str(artifact_dir) not in response.text


def test_h2_runtime_does_not_fallback_to_an_available_h1_artifact(monkeypatch, artifact_dir):
    legacy_path = artifact_dir / "electricity_nem_daily_demand_rf.joblib"
    joblib.dump({"artifact_version": 1, "feature_names": ["demand_lag_1"]}, legacy_path)
    monkeypatch.setattr(nem_model, "nem_artifact_path", lambda: legacy_path)
    monkeypatch.setattr(nem_model, "nem_h2_artifact_path", lambda: artifact_dir / "missing-h2.joblib")

    with pytest.raises(FileNotFoundError, match="artifact is missing"):
        nem_model._load_artifact()


def test_prediction_schema_rejects_training_target_after_cutoff():
    payload = make_payload()
    last_sample = payload["training_samples"][-1]
    last_sample["cutoff_date"] = "2026-11-25"
    last_sample["target_date"] = "2026-11-27"
    payload["training_end"] = "2026-11-27"

    with pytest.raises(ValueError, match="targets after the complete-data cutoff"):
        nem_model.NEMPredictionRequest.model_validate(payload)


def test_prediction_and_classification_schema_accept_cutoff_and_reject_brisbane_future_observation():
    from service_apps.classification.schemas import NEMClassificationRequest

    valid = make_payload()
    assert nem_model.NEMPredictionRequest.model_validate(valid).observation_end == date(2026, 11, 25)
    assert NEMClassificationRequest.model_validate(valid).observation_end == date(2026, 11, 25)

    # 14:00 UTC is the next calendar day in Brisbane (+10:00), beyond cutoff.
    invalid = {**valid, "observations": [*valid["observations"], {
        "observed_at": "2026-11-25T14:00:00+00:00",
        "value": "18000", "unit": "MW", "result": "Demand",
    }], "observation_count": valid["observation_count"] + 1, "observation_end": "2026-11-26"}
    for schema in (nem_model.NEMPredictionRequest, NEMClassificationRequest):
        with pytest.raises(ValueError, match="after cutoff_date in Brisbane time"):
            schema.model_validate(invalid)


def test_prediction_internal_api_rejects_utc_observation_after_brisbane_cutoff(monkeypatch):
    monkeypatch.setenv("PREDICTION_SERVICE_SECRET", SECRET)
    payload = make_payload()
    payload["observations"] = [*payload["observations"], {
        "observed_at": "2026-11-25T14:00:00+00:00",
        "value": "18000", "unit": "MW", "result": "Demand",
    }]
    payload["observation_count"] += 1
    payload["observation_end"] = "2026-11-26"

    response = TestClient(app).post(
        "/internal/prediction/nem/train", json=payload, headers=HEADERS
    )
    assert response.status_code == 422
    assert "after cutoff_date in Brisbane time" in response.text


def test_prediction_h2_path_guard_allows_distinct_paths_and_rejects_aliases(monkeypatch, tmp_path):
    h1 = tmp_path / "model-h1.joblib"
    h2 = tmp_path / "model-h2.joblib"
    monkeypatch.setattr(nem_model, "nem_artifact_path", lambda: h1)
    monkeypatch.setattr(nem_model, "nem_h2_artifact_path", lambda: h2)
    nem_model._ensure_h2_artifact_path_is_distinct()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(nem_model, "nem_artifact_path", lambda: h1.resolve())
    monkeypatch.setattr(nem_model, "nem_h2_artifact_path", lambda: Path("model-h1.joblib"))
    with pytest.raises(ValueError, match="H2 Prediction artifact path must be different"):
        nem_model._ensure_h2_artifact_path_is_distinct()


def test_prediction_h2_collision_guard_runs_before_model_fit_or_artifact_write(monkeypatch, tmp_path):
    same_path = tmp_path / "protected-h1.joblib"
    monkeypatch.setattr(nem_model, "nem_artifact_path", lambda: same_path)
    monkeypatch.setattr(nem_model, "nem_h2_artifact_path", lambda: same_path.parent / "." / same_path.name)
    monkeypatch.setattr(nem_model, "_new_model", lambda: (_ for _ in ()).throw(AssertionError("fit must not start")))

    with pytest.raises(ValueError, match="H2 Prediction artifact path must be different"):
        nem_model.train_nem_daily_model(nem_model.NEMPredictionRequest.model_validate(make_payload()))
    assert not same_path.exists()


def test_prediction_h2_path_guard_handles_windows_case_insensitivity(monkeypatch, tmp_path):
    import os

    if os.name != "nt":
        pytest.skip("Windows path case folding is platform-specific")
    path = tmp_path / "Model-H1.joblib"
    monkeypatch.setattr(nem_model, "nem_artifact_path", lambda: path)
    monkeypatch.setattr(nem_model, "nem_h2_artifact_path", lambda: path.with_name("model-h1.joblib"))
    with pytest.raises(ValueError, match="H2 Prediction artifact path must be different"):
        nem_model._ensure_h2_artifact_path_is_distinct()


def test_prediction_h2_path_guard_rejects_symlink_alias(monkeypatch, tmp_path):
    target = tmp_path / "protected-model.joblib"
    target.write_bytes(b"test placeholder")
    alias = tmp_path / "model-alias.joblib"
    try:
        alias.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is unavailable in this environment")
    monkeypatch.setattr(nem_model, "nem_artifact_path", lambda: target)
    monkeypatch.setattr(nem_model, "nem_h2_artifact_path", lambda: alias)
    with pytest.raises(ValueError, match="H2 Prediction artifact path must be different"):
        nem_model._ensure_h2_artifact_path_is_distinct()


def test_run_nem_daily_forecast_returns_payload_dataset_provenance(monkeypatch):
    payload = make_payload()

    class ForecastModel:
        def predict(self, _features):
            return [18000.0]

    artifact = {
        "dataset_id": payload["dataset_id"],
        "dataset_name": payload["dataset_name"],
        "dataset_source": payload["dataset_source"],
        "network_code": payload["network_code"],
        "metric": payload["metric"],
        "interval": payload["interval"],
        "unit": payload["unit"],
        "training_data_fingerprint": "c" * 64,
        "model": ForecastModel(),
    }
    monkeypatch.setattr(nem_model, "_load_artifact", lambda: (artifact, Path("nem-model-h2.joblib")))

    result = nem_model.run_nem_daily_forecast(nem_model.NEMPredictionRequest.model_validate(payload))

    assert result["dataset_provenance"] == {
        "dataset_id": payload["dataset_id"],
        "dataset_name": payload["dataset_name"],
        "dataset_source": payload["dataset_source"],
        "network_code": payload["network_code"],
        "metric": payload["metric"],
        "interval": payload["interval"],
        "unit": payload["unit"],
    }
