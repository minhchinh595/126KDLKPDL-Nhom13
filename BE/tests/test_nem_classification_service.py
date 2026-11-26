from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import platform
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import numpy as np
import joblib
import pytest
from fastapi.testclient import TestClient
from sklearn.model_selection import TimeSeriesSplit
import sklearn

from app.classification import nem_classifier
from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE
from app.services.nem_ml_data import DailyObservation, NEMDailyMLData, build_nem_prediction_payload
from service_apps.prediction.schemas import NEMPredictionRequest
from service_apps.classification.main import app


SECRET = "nem-classification-test-secret-at-least-32-bytes"
HEADERS = {"X-Classification-Service-Secret": SECRET}
BRISBANE = ZoneInfo("Australia/Brisbane")


def make_payload(days=365, *, now=None):
    end = date(2026, 11, 25) + timedelta(days=days - 365)
    now = now or datetime(2026, 11, 26, 12, tzinfo=BRISBANE)
    start = end - timedelta(days=days - 1)
    observations = tuple(
        DailyObservation(
            datetime.combine(start + timedelta(days=index), datetime.min.time(), tzinfo=BRISBANE),
            Decimal(str(15500 + index * 2 + (index % 7) * 75 + (index % 31) * 4)),
            "MW",
            "Demand",
        )
        for index in range(days)
    )
    data = NEMDailyMLData(
        dataset_id=83,
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
    with TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
        yield Path(directory)


def test_binary_labels_use_low_at_median_and_high_above():
    assert nem_classifier._labels([20.0, 30.0, 30.01], 30.0) == ["Low", "Low", "High"]


def test_each_fold_threshold_comes_only_from_chronological_training_split():
    payload = NEMPredictionRequest.model_validate(make_payload())
    report = nem_classifier._evaluate(payload)
    targets = np.asarray([sample.target for sample in payload.training_samples])
    splits = TimeSeriesSplit(n_splits=4, test_size=28, gap=1)
    assert report["shuffle"] is False
    assert len(report["folds"]) == 4
    for fold, (train_indices, validation_indices) in zip(report["folds"], splits.split(targets)):
        threshold = float(np.median(targets[train_indices]))
        assert fold["threshold_mw"] == threshold
        assert fold["training_period"]["sample_count"] == len(train_indices)
        assert fold["validation_period"]["sample_count"] == len(validation_indices) == 28
        assert date.fromisoformat(fold["training_period"]["end"]) + timedelta(days=2) <= date.fromisoformat(fold["validation_period"]["start"])
        # The generated increasing demand series ensures future validation values
        # would change the median, guarding against calculating it on all samples.
        assert threshold != float(np.median(targets))
        assert set(fold["class_distribution"]["training"]) == {"Low", "High"}
        assert fold["random_forest"]["confusion_matrix"]["labels"] == ["Low", "High"]
        assert sum(map(sum, fold["random_forest"]["confusion_matrix"]["matrix"])) == 28
        assert "accuracy" in fold["random_forest"]
        assert "precision_high" in fold["random_forest"]
        assert "recall_high" in fold["random_forest"]
        assert "macro_f1" in fold["random_forest"]
        assert "majority_class_baseline" in fold


def test_classification_train_run_artifact_and_run_without_fit(monkeypatch, artifact_dir):
    monkeypatch.setenv("CLASSIFICATION_SERVICE_SECRET", SECRET)
    path = artifact_dir / "nem-classifier-h2.joblib"
    monkeypatch.setattr(nem_classifier, "nem_h2_artifact_path", lambda: path)
    monkeypatch.setattr(nem_classifier, "nem_artifact_path", lambda: artifact_dir / "nem-classifier-h1.joblib")
    client = TestClient(app)
    payload = make_payload()
    trained = client.post("/internal/classification/nem/train", json=payload, headers=HEADERS)
    assert trained.status_code == 200, trained.text
    result = trained.json()
    assert result["threshold_rule"] == "Low if demand <= training median; High otherwise"
    assert result["unit"] == "MW"
    assert result["labels"] == ["Low", "High"]
    assert result["training_sample_count"] == 336
    assert result["forecast_horizon_days"] == 2
    assert result["feature_schema_version"] == "nem_daily_demand_h2_v1"
    assert path.is_file()
    metadata = result["model_provenance"]
    assert metadata["model_type"] == "classification"
    assert metadata["artifact_name"] == "nem-classifier-h2.joblib"
    assert metadata["artifact_format"] == "joblib"
    assert metadata["artifact_version"] == nem_classifier.ARTIFACT_VERSION
    assert metadata["contract_version"] == nem_classifier.CONTRACT_VERSION
    assert metadata["python_version"] == platform.python_version()
    assert metadata["sklearn_version"] == sklearn.__version__
    assert metadata["trained_at"].endswith("+00:00")
    assert metadata["model_parameters"] == nem_classifier.MODEL_PARAMETERS
    assert "secret" not in str(metadata).lower()
    artifact = joblib.load(path)
    assert artifact["trained_at"] == metadata["trained_at"]

    def forbidden_fit():
        raise AssertionError("Run must not construct or fit a classifier")

    monkeypatch.setattr(nem_classifier, "_new_model", forbidden_fit)
    monkeypatch.setattr(nem_classifier, "nem_h2_artifact_path", lambda: path)
    forecast = client.post("/internal/classification/nem/run", json=payload, headers=HEADERS)
    assert forecast.status_code == 200, forecast.text
    result = forecast.json()
    assert result["forecast_date"] == "2026-11-27"
    assert result["cutoff_date"] == "2026-11-25"
    assert result["horizon_days"] == 2
    assert result["predicted_level"] in {"Low", "High"}
    assert result["unit"] == "MW"
    assert result["threshold_mw"] > 0
    assert result["last_observed_at"].endswith("+10:00")
    assert result["training_data_fingerprint"] == result["run_data_fingerprint"]
    assert result["dataset_provenance"]["dataset_source"] == NEM_DATASET_SOURCE

    new_dates = make_payload(days=367, now=datetime(2026, 11, 27, 12, tzinfo=BRISBANE))
    next_run = client.post("/internal/classification/nem/run", json=new_dates, headers=HEADERS)
    assert next_run.status_code == 200, next_run.text
    assert next_run.json()["forecast_date"] == "2026-11-28"
    assert next_run.json()["run_data_fingerprint"] != next_run.json()["training_data_fingerprint"]


def test_classification_service_auth_and_provenance_checks(monkeypatch, artifact_dir):
    monkeypatch.setenv("CLASSIFICATION_SERVICE_SECRET", SECRET)
    path = artifact_dir / "nem-classifier-h2.joblib"
    monkeypatch.setattr(nem_classifier, "nem_h2_artifact_path", lambda: path)
    monkeypatch.setattr(nem_classifier, "nem_artifact_path", lambda: artifact_dir / "nem-classifier-h1.joblib")
    client = TestClient(app)
    payload = make_payload()
    assert client.post("/internal/classification/nem/train", json=payload).status_code == 401
    assert client.post("/internal/classification/nem/train", json=payload, headers=HEADERS).status_code == 200
    monkeypatch.setattr(nem_classifier, "nem_h2_artifact_path", lambda: path)
    wrong_unit = {**payload, "unit": "MWh"}
    assert client.post("/internal/classification/nem/run", json=wrong_unit, headers=HEADERS).status_code == 422
    wrong_features = {**payload, "feature_names": ["demand_at_cutoff"]}
    assert client.post("/internal/classification/nem/run", json=wrong_features, headers=HEADERS).status_code == 422
    wrong_dataset = {**payload, "dataset_id": payload["dataset_id"] + 1}
    mismatch = client.post("/internal/classification/nem/run", json=wrong_dataset, headers=HEADERS)
    assert mismatch.status_code == 409
    assert str(artifact_dir) not in mismatch.text


def test_classification_run_missing_artifact_is_not_reported_as_not_ready(monkeypatch, artifact_dir):
    monkeypatch.setenv("CLASSIFICATION_SERVICE_SECRET", SECRET)
    monkeypatch.setattr(nem_classifier, "nem_h2_artifact_path", lambda: artifact_dir / "absent-h2.joblib")
    legacy_path = artifact_dir / "available-h1.joblib"
    joblib.dump({"artifact_version": 1}, legacy_path)
    monkeypatch.setattr(nem_classifier, "nem_artifact_path", lambda: legacy_path)
    response = TestClient(app).post(
        "/internal/classification/nem/run", json=make_payload(), headers=HEADERS
    )
    assert response.status_code == 409
    assert "artifact is missing" in response.text
    assert "not_ready" not in response.text


def test_h2_classifier_runtime_does_not_fallback_to_an_available_h1_artifact(monkeypatch, artifact_dir):
    legacy_path = artifact_dir / "electricity_nem_daily_demand_classifier.joblib"
    joblib.dump({"artifact_version": 1, "feature_names": ["demand_lag_1"]}, legacy_path)
    monkeypatch.setattr(nem_classifier, "nem_artifact_path", lambda: legacy_path)
    monkeypatch.setattr(nem_classifier, "nem_h2_artifact_path", lambda: artifact_dir / "missing-h2.joblib")

    with pytest.raises(FileNotFoundError, match="artifact is missing"):
        nem_classifier._load_artifact()


def test_classifier_does_not_accept_missing_forecast_feature_as_zero():
    payload = NEMPredictionRequest.model_validate(make_payload())
    invalid = payload.model_copy(deep=True)
    invalid.forecast.features["demand_27d_before_cutoff"] = 0.0
    with pytest.raises(ValueError, match="forecast features do not match"):
        nem_classifier._validate_payload_features(invalid)


def test_classification_h2_path_guard_allows_distinct_and_rejects_relative_absolute_collision(monkeypatch, tmp_path):
    h1 = tmp_path / "classifier-h1.joblib"
    h2 = tmp_path / "classifier-h2.joblib"
    monkeypatch.setattr(nem_classifier, "nem_artifact_path", lambda: h1)
    monkeypatch.setattr(nem_classifier, "nem_h2_artifact_path", lambda: h2)
    nem_classifier._ensure_h2_artifact_path_is_distinct()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(nem_classifier, "nem_artifact_path", lambda: h1.resolve())
    monkeypatch.setattr(nem_classifier, "nem_h2_artifact_path", lambda: Path("classifier-h1.joblib"))
    with pytest.raises(ValueError, match="H2 Classification artifact path must be different"):
        nem_classifier._ensure_h2_artifact_path_is_distinct()


def test_classification_h2_collision_guard_runs_before_model_fit_or_artifact_write(monkeypatch, tmp_path):
    same_path = tmp_path / "protected-h1.joblib"
    monkeypatch.setattr(nem_classifier, "nem_artifact_path", lambda: same_path)
    monkeypatch.setattr(nem_classifier, "nem_h2_artifact_path", lambda: same_path.parent / "." / same_path.name)
    monkeypatch.setattr(nem_classifier, "_new_model", lambda: (_ for _ in ()).throw(AssertionError("fit must not start")))

    with pytest.raises(ValueError, match="H2 Classification artifact path must be different"):
        nem_classifier.train_nem_daily_classifier(NEMPredictionRequest.model_validate(make_payload()))
    assert not same_path.exists()


def test_classification_h2_path_guard_handles_windows_case_insensitivity(monkeypatch, tmp_path):
    import os

    if os.name != "nt":
        pytest.skip("Windows path case folding is platform-specific")
    path = tmp_path / "Classifier-H1.joblib"
    monkeypatch.setattr(nem_classifier, "nem_artifact_path", lambda: path)
    monkeypatch.setattr(nem_classifier, "nem_h2_artifact_path", lambda: path.with_name("classifier-h1.joblib"))
    with pytest.raises(ValueError, match="H2 Classification artifact path must be different"):
        nem_classifier._ensure_h2_artifact_path_is_distinct()


def test_classification_h2_path_guard_rejects_symlink_alias(monkeypatch, tmp_path):
    target = tmp_path / "protected-classifier.joblib"
    target.write_bytes(b"test placeholder")
    alias = tmp_path / "classifier-alias.joblib"
    try:
        alias.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is unavailable in this environment")
    monkeypatch.setattr(nem_classifier, "nem_artifact_path", lambda: target)
    monkeypatch.setattr(nem_classifier, "nem_h2_artifact_path", lambda: alias)
    with pytest.raises(ValueError, match="H2 Classification artifact path must be different"):
        nem_classifier._ensure_h2_artifact_path_is_distinct()


def test_classification_internal_api_rejects_utc_observation_after_brisbane_cutoff(monkeypatch):
    monkeypatch.setenv("CLASSIFICATION_SERVICE_SECRET", SECRET)
    payload = make_payload()
    payload["observations"] = [*payload["observations"], {
        "observed_at": "2026-11-25T14:00:00+00:00",
        "value": "18000", "unit": "MW", "result": "Demand",
    }]
    payload["observation_count"] += 1
    payload["observation_end"] = "2026-11-26"

    response = TestClient(app).post(
        "/internal/classification/nem/train", json=payload, headers=HEADERS
    )
    assert response.status_code == 422
    assert "after cutoff_date in Brisbane time" in response.text
