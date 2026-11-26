"""NEM daily demand forecasting, isolated from the legacy monthly VNM model."""

from __future__ import annotations

import hashlib
import json
import math
import os
import os.path
import platform
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import TimeSeriesSplit

from service_apps.prediction.schemas import (
    NEM_BRISBANE,
    NEM_FEATURE_NAMES,
    NEM_FEATURE_UNITS,
    NEMPredictionRequest,
)
from app.services.nem_ml_contract import NEM_FEATURE_SCHEMA_VERSION, NEM_FORECAST_HORIZON_DAYS


ARTIFACT_VERSION = 2
CONTRACT_VERSION = 2
ALGORITHM = "RandomForestRegressor"
MODEL_PARAMETERS = {
    "n_estimators": 200,
    "min_samples_leaf": 3,
    "random_state": 42,
    "n_jobs": 1,
}
FOLD_COUNT = 4
FOLD_SIZE = 28
MIN_TRAINING_FOLD_SAMPLES = 60


def nem_artifact_path() -> Path:
    """Return the legacy H1 artifact path used only for collision protection."""
    configured = os.getenv("NEM_PREDICTION_MODEL_PATH")
    if configured:
        return Path(configured)
    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / "artifacts" / "electricity_nem_daily_demand_rf.joblib"


def nem_h2_artifact_path() -> Path:
    """Versioned fixed two-day artifact path; never aliases the legacy artifact."""
    configured = os.getenv("NEM_PREDICTION_MODEL_PATH_H2")
    if configured:
        return Path(configured)
    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / "artifacts" / "electricity_nem_daily_demand_rf_h2.joblib"


def _ensure_h2_artifact_path_is_distinct() -> None:
    """Refuse training if the H2 output could overwrite the configured H1 file."""
    h1_path = nem_artifact_path().expanduser()
    h2_path = nem_h2_artifact_path().expanduser()
    try:
        h1_resolved = h1_path.resolve(strict=False)
        h2_resolved = h2_path.resolve(strict=False)
        same_path = os.path.normcase(os.path.normpath(str(h1_resolved))) == os.path.normcase(
            os.path.normpath(str(h2_resolved))
        )
        if not same_path and h1_resolved.exists() and h2_resolved.exists():
            same_path = h1_resolved.samefile(h2_resolved)
    except (OSError, RuntimeError) as exc:
        raise ValueError("Could not safely resolve H1 and H2 Prediction artifact paths") from exc
    if same_path:
        raise ValueError("H2 Prediction artifact path must be different from the H1 artifact path")


def _canonical_fingerprint(payload: NEMPredictionRequest) -> str:
    canonical = {
        "dataset_id": payload.dataset_id,
        "dataset_name": payload.dataset_name,
        "dataset_source": payload.dataset_source,
        "network_code": payload.network_code,
        "metric": payload.metric,
        "interval": payload.interval,
        "unit": payload.unit,
        "observations": [
            {
                "observed_at": row.observed_at.isoformat(),
                "value": str(row.value),
                "unit": row.unit,
                "result": row.result,
            }
            for row in payload.observations
        ],
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_training_payload(payload: NEMPredictionRequest) -> None:
    if payload.data_fingerprint != _canonical_fingerprint(payload):
        raise ValueError("NEM prediction data fingerprint does not match observations")
    values_by_date: dict[date, float] = {}
    for row in payload.observations:
        local_day = row.observed_at.astimezone(NEM_BRISBANE).date()
        values_by_date[local_day] = float(row.value)

    expected_samples = []
    for target_day in sorted(day for day in values_by_date if day <= payload.cutoff_date):
        cutoff_day = target_day - timedelta(days=NEM_FORECAST_HORIZON_DAYS)
        feature_days = (cutoff_day, cutoff_day - timedelta(days=6), cutoff_day - timedelta(days=13), cutoff_day - timedelta(days=27))
        if not all(day in values_by_date for day in feature_days):
            continue
        features = dict(zip(NEM_FEATURE_NAMES[:4], (values_by_date[day] for day in feature_days)))
        features["day_of_week"] = float(target_day.weekday())
        features["day_of_year"] = float(target_day.timetuple().tm_yday)
        expected_samples.append((cutoff_day, target_day, features, values_by_date[target_day]))

    supplied = payload.training_samples
    if len(expected_samples) != len(supplied):
        raise ValueError("supervised sample set does not match NEM observations")
    for expected, sample in zip(expected_samples, supplied):
        cutoff_day, target_day, features, target = expected
        if sample.cutoff_date != cutoff_day or sample.target_date != target_day or not math.isclose(sample.target, target, rel_tol=1e-12):
            raise ValueError("supervised sample target does not match NEM observations")
        if set(sample.features) != set(NEM_FEATURE_NAMES) or any(
            not math.isclose(sample.features[key], features[key], rel_tol=1e-12, abs_tol=1e-12)
            for key in NEM_FEATURE_NAMES
        ):
            raise ValueError("supervised sample features do not match prior NEM observations")

    if payload.forecast is not None:
        cutoff = payload.forecast.cutoff_date
        feature_days = (cutoff, cutoff - timedelta(days=6), cutoff - timedelta(days=13), cutoff - timedelta(days=27))
        if any(day > cutoff for day in feature_days):
            raise ValueError("forecast feature date exceeds cutoff_date")
        if any(day not in values_by_date for day in feature_days):
            raise ValueError("forecast features are not ready for the required cutoff dates")
        expected_forecast = dict(zip(NEM_FEATURE_NAMES[:4], (values_by_date[day] for day in feature_days)))
        expected_forecast["day_of_week"] = float(payload.forecast.forecast_date.weekday())
        expected_forecast["day_of_year"] = float(payload.forecast.forecast_date.timetuple().tm_yday)
        if any(not math.isclose(payload.forecast.features[key], expected_forecast[key], rel_tol=1e-12, abs_tol=1e-12) for key in NEM_FEATURE_NAMES):
            raise ValueError("forecast features do not match observations on or before cutoff_date")


def _metric_values(actual: list[float], predicted: list[float]) -> dict[str, float | None]:
    if not actual:
        return {"mae_mw": None, "rmse_mw": None, "mape_pct": None, "sample_count": 0}
    errors = [prediction - truth for truth, prediction in zip(actual, predicted)]
    mape = None
    if actual and all(abs(value) > 1e-9 for value in actual):
        mape = mean(abs(error) / abs(truth) for error, truth in zip(errors, actual)) * 100
    return {
        "mae_mw": round(mean(abs(error) for error in errors), 6),
        "rmse_mw": round(math.sqrt(mean(error * error for error in errors)), 6),
        "mape_pct": round(mape, 6) if mape is not None else None,
        "sample_count": len(actual),
    }


def _new_model() -> RandomForestRegressor:
    return RandomForestRegressor(**MODEL_PARAMETERS)


def _evaluate(payload: NEMPredictionRequest) -> dict[str, Any]:
    samples = payload.training_samples
    sample_count = len(samples)
    minimum = FOLD_COUNT * FOLD_SIZE + MIN_TRAINING_FOLD_SAMPLES
    if sample_count < minimum:
        raise ValueError(
            f"At least {minimum} complete supervised samples are required for chronological evaluation; got {sample_count}"
        )
    x = np.asarray([[row.features[name] for name in NEM_FEATURE_NAMES] for row in samples], dtype=float)
    y = np.asarray([row.target for row in samples], dtype=float)
    # Embargo the validation day's C+1 label so training is available at cutoff C.
    splitter = TimeSeriesSplit(n_splits=FOLD_COUNT, test_size=FOLD_SIZE, gap=1)
    fold_results = []
    pooled_actual: list[float] = []
    pooled_rf: list[float] = []
    pooled_persistence: list[float] = []
    pooled_seasonal: list[float] = []
    pooled_seasonal_actual: list[float] = []
    values_by_date = {
        row.observed_at.astimezone(NEM_BRISBANE).date(): float(row.value)
        for row in payload.observations
    }
    for fold_index, (train_indices, test_indices) in enumerate(splitter.split(x), start=1):
        if len(train_indices) < MIN_TRAINING_FOLD_SAMPLES:
            raise ValueError("chronological evaluation produced an undersized training fold")
        estimator = _new_model()
        estimator.fit(x[train_indices], y[train_indices])
        actual = y[test_indices].astype(float).tolist()
        predicted = estimator.predict(x[test_indices]).astype(float).tolist()
        dates = [samples[index].target_date for index in test_indices]
        persistence = [float(samples[index].features["demand_at_cutoff"]) for index in test_indices]
        seasonal_pairs = [
            (float(y[index]), values_by_date[samples[index].target_date - timedelta(days=7)])
            for index in test_indices
            if samples[index].target_date - timedelta(days=7) in values_by_date
        ]
        seasonal_actual = [pair[0] for pair in seasonal_pairs]
        seasonal = [pair[1] for pair in seasonal_pairs]
        fold_results.append({
            "fold": fold_index,
            "training_sample_count": len(train_indices),
            "training_start": samples[int(train_indices[0])].target_date.isoformat(),
            "training_end": samples[int(train_indices[-1])].target_date.isoformat(),
            "validation_sample_count": len(test_indices),
            "validation_start": dates[0].isoformat(),
            "validation_end": dates[-1].isoformat(),
            "random_forest": _metric_values(actual, predicted),
            "persistence_baseline": _metric_values(actual, persistence),
            "seasonal_naive_7d_baseline": _metric_values(seasonal_actual, seasonal),
        })
        pooled_actual.extend(actual)
        pooled_rf.extend(predicted)
        pooled_persistence.extend(persistence)
        pooled_seasonal.extend(seasonal)
        pooled_seasonal_actual.extend(seasonal_actual)

    overall = {
        "random_forest": _metric_values(pooled_actual, pooled_rf),
        "persistence_baseline": _metric_values(pooled_actual, pooled_persistence),
        "seasonal_naive_7d_baseline": _metric_values(pooled_seasonal_actual, pooled_seasonal),
    }
    mae_values = {name: metrics["mae_mw"] for name, metrics in overall.items()}
    winner = min(mae_values, key=mae_values.get)
    return {
        "strategy": "TimeSeriesSplit chronological rolling-origin",
        "shuffle": False,
        "fold_count": len(fold_results),
        "fold_size": FOLD_SIZE,
        "folds": fold_results,
        "overall": overall,
        "lowest_mae_method": winner,
        "mape_note": "MAPE is omitted when any evaluated actual demand is zero or near zero.",
    }


def train_nem_daily_model(payload: NEMPredictionRequest) -> dict[str, Any]:
    _ensure_h2_artifact_path_is_distinct()
    _validate_training_payload(payload)
    validation = _evaluate(payload)
    x = np.asarray(
        [[row.features[name] for name in NEM_FEATURE_NAMES] for row in payload.training_samples],
        dtype=float,
    )
    y = np.asarray([row.target for row in payload.training_samples], dtype=float)
    final_model = _new_model()
    final_model.fit(x, y)
    artifact_path = nem_h2_artifact_path()
    trained_at = datetime.now(timezone.utc).isoformat()
    artifact = {
        "artifact_version": ARTIFACT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "horizon_days": NEM_FORECAST_HORIZON_DAYS,
        "feature_schema_version": NEM_FEATURE_SCHEMA_VERSION,
        "cutoff_target_contract": "Brisbane as_of_date - 1 cutoff; as_of_date + 1 target",
        "model": final_model,
        "algorithm": ALGORITHM,
        "algorithm_version": sklearn.__version__,
        "python_version": platform.python_version(),
        "trained_at": trained_at,
        "model_parameters": MODEL_PARAMETERS.copy(),
        "feature_names": list(NEM_FEATURE_NAMES),
        "feature_units": NEM_FEATURE_UNITS.copy(),
        "dataset_id": payload.dataset_id,
        "dataset_name": payload.dataset_name,
        "dataset_source": payload.dataset_source,
        "network_code": payload.network_code,
        "metric": payload.metric,
        "interval": payload.interval,
        "unit": payload.unit,
        "observation_start": payload.observation_start.isoformat(),
        "observation_end": payload.observation_end.isoformat(),
        "training_start": payload.training_start.isoformat() if payload.training_start else None,
        "training_end": payload.training_end.isoformat() if payload.training_end else None,
        "observation_count": payload.observation_count,
        "training_sample_count": payload.training_sample_count,
        "training_data_fingerprint": payload.data_fingerprint,
        "validation": validation,
    }
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(prefix=artifact_path.name, suffix=".tmp", dir=artifact_path.parent, delete=False) as tmp:
            temp_name = tmp.name
        joblib.dump(artifact, temp_name)
        Path(temp_name).replace(artifact_path)
    finally:
        if temp_name and Path(temp_name).exists():
            Path(temp_name).unlink()
    return {
        "stage": "training",
        "dataset_id": payload.dataset_id,
        "dataset_name": payload.dataset_name,
        "dataset_source": payload.dataset_source,
        "model_name": ALGORITHM,
        "target": "daily_demand",
        "unit": "MW",
        "network_code": "NEM",
        "metric": payload.metric,
        "interval": "1d",
        "observation_start": payload.observation_start.isoformat(),
        "observation_end": payload.observation_end.isoformat(),
        "forecast_horizon_days": NEM_FORECAST_HORIZON_DAYS,
        "feature_schema_version": NEM_FEATURE_SCHEMA_VERSION,
        "feature_names": list(NEM_FEATURE_NAMES),
        "training_sample_count": payload.training_sample_count,
        "training_start": payload.training_start.isoformat(),
        "training_end": payload.training_end.isoformat(),
        "training_data_fingerprint": payload.data_fingerprint,
        "validation": validation,
        "artifact_name": artifact_path.name,
        "model_provenance": {
            "model_type": "prediction",
            "model_name": ALGORITHM,
            "artifact_name": artifact_path.name,
            "artifact_format": "joblib",
            "artifact_version": artifact["artifact_version"],
            "contract_version": artifact["contract_version"],
            "horizon_days": artifact["horizon_days"],
            "feature_schema_version": artifact["feature_schema_version"],
            "python_version": artifact["python_version"],
            "sklearn_version": artifact["algorithm_version"],
            "trained_at": artifact["trained_at"],
            "model_parameters": artifact["model_parameters"],
        },
    }


def _load_artifact() -> tuple[dict[str, Any], Path]:
    # NEM fixed-horizon inference must use the matching H2 artifact. The H1
    # path remains separate and is never used as a fallback here.
    artifact_path = nem_h2_artifact_path()
    if not artifact_path.is_file():
        raise FileNotFoundError("NEM prediction artifact is missing")
    try:
        artifact = joblib.load(artifact_path)
    except Exception as exc:
        raise ValueError("NEM prediction artifact cannot be loaded") from exc
    if not isinstance(artifact, dict) or artifact.get("artifact_version") != ARTIFACT_VERSION:
        raise ValueError("NEM prediction artifact is incompatible")
    expected = {
        "algorithm": ALGORITHM,
        "feature_names": list(NEM_FEATURE_NAMES),
        "feature_units": NEM_FEATURE_UNITS,
        "network_code": "NEM",
        "metric": "demand",
        "interval": "1d",
        "unit": "MW",
        "contract_version": CONTRACT_VERSION,
        "horizon_days": NEM_FORECAST_HORIZON_DAYS,
        "feature_schema_version": NEM_FEATURE_SCHEMA_VERSION,
        "cutoff_target_contract": "Brisbane as_of_date - 1 cutoff; as_of_date + 1 target",
    }
    if any(artifact.get(key) != value for key, value in expected.items()):
        raise ValueError("NEM prediction artifact is incompatible")
    if not hasattr(artifact.get("model"), "predict"):
        raise ValueError("NEM prediction artifact is incompatible")
    return artifact, artifact_path


def run_nem_daily_forecast(payload: NEMPredictionRequest) -> dict[str, Any]:
    if payload.forecast_status != "ready" or payload.forecast is None:
        raise ValueError("NEM forecast data is not ready")
    artifact, artifact_path = _load_artifact()
    identity = ("dataset_id", "dataset_name", "dataset_source", "network_code", "metric", "interval", "unit")
    if any(getattr(payload, key) != artifact.get(key) for key in identity):
        raise ValueError("NEM prediction artifact dataset identity does not match current data")
    _validate_training_payload(payload)
    forecast = payload.forecast
    values = np.asarray([[forecast.features[name] for name in NEM_FEATURE_NAMES]], dtype=float)
    prediction = float(artifact["model"].predict(values)[0])
    if not math.isfinite(prediction) or prediction < 0:
        raise ValueError("NEM prediction model returned an invalid demand value")
    return {
        "stage": "forecast",
        "forecast_status": "ready",
        "model_name": ALGORITHM,
        "target": "daily_demand",
        "network_code": "NEM",
        "metric": "demand",
        "interval": "1d",
        "forecast_date": forecast.forecast_date.isoformat(),
        "as_of_date": forecast.as_of_date.isoformat(),
        "cutoff_date": forecast.cutoff_date.isoformat(),
        "horizon_days": NEM_FORECAST_HORIZON_DAYS,
        "predicted_demand": round(prediction, 6),
        "unit": "MW",
        "last_observed_date": forecast.last_observed_date.isoformat(),
        "last_observed_at": forecast.last_observed_at.isoformat(),
        "training_data_fingerprint": artifact["training_data_fingerprint"],
        "run_data_fingerprint": payload.data_fingerprint,
        "artifact_name": artifact_path.name,
        "dataset_provenance": {
            "dataset_id": payload.dataset_id,
            "dataset_name": payload.dataset_name,
            "dataset_source": payload.dataset_source,
            "network_code": payload.network_code,
            "metric": payload.metric,
            "interval": payload.interval,
            "unit": payload.unit,
        },
    }
