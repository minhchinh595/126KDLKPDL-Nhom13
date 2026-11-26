"""NEM daily binary demand classification, separate from the legacy VNM model."""

from __future__ import annotations

import hashlib
import json
import math
import os
import os.path
import platform
import tempfile
from collections import Counter
from datetime import date, timedelta
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
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
MODEL_NAME = "RandomForestClassifier"
LABELS = ("Low", "High")
POSITIVE_LABEL = "High"
MODEL_PARAMETERS = {
    "n_estimators": 300,
    "min_samples_leaf": 2,
    "class_weight": "balanced",
    "random_state": 42,
    "n_jobs": 1,
}
FOLD_COUNT = 4
FOLD_SIZE = 28
MIN_TRAINING_FOLD_SAMPLES = 60


def nem_artifact_path() -> Path:
    """Return the legacy H1 artifact path used only for collision protection."""
    configured = os.getenv("NEM_CLASSIFICATION_MODEL_PATH")
    if configured:
        return Path(configured)
    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / "artifacts" / "electricity_nem_daily_demand_classifier.joblib"


def nem_h2_artifact_path() -> Path:
    """Versioned fixed two-day artifact path; never aliases the legacy artifact."""
    configured = os.getenv("NEM_CLASSIFICATION_MODEL_PATH_H2")
    if configured:
        return Path(configured)
    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / "artifacts" / "electricity_nem_daily_demand_classifier_h2.joblib"


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
        raise ValueError("Could not safely resolve H1 and H2 Classification artifact paths") from exc
    if same_path:
        raise ValueError("H2 Classification artifact path must be different from the H1 artifact path")


def _fingerprint(payload: NEMPredictionRequest) -> str:
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


def _validated_daily_values(payload: NEMPredictionRequest) -> dict[date, float]:
    if payload.data_fingerprint != _fingerprint(payload):
        raise ValueError("NEM classification data fingerprint does not match observations")
    values: dict[date, float] = {}
    for row in payload.observations:
        local_day = row.observed_at.astimezone(NEM_BRISBANE).date()
        if local_day in values:
            raise ValueError(f"duplicate NEM demand date: {local_day}")
        value = float(row.value)
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"invalid NEM demand on {local_day}")
        values[local_day] = value
    return values


def _validate_payload_features(payload: NEMPredictionRequest) -> None:
    values = _validated_daily_values(payload)
    expected_samples = []
    for target_day in sorted(day for day in values if day <= payload.cutoff_date):
        cutoff_day = target_day - timedelta(days=NEM_FORECAST_HORIZON_DAYS)
        feature_days = (cutoff_day, cutoff_day - timedelta(days=6), cutoff_day - timedelta(days=13), cutoff_day - timedelta(days=27))
        if not all(day in values for day in feature_days):
            continue
        row = dict(zip(NEM_FEATURE_NAMES[:4], (values[day] for day in feature_days)))
        row["day_of_week"] = float(target_day.weekday())
        row["day_of_year"] = float(target_day.timetuple().tm_yday)
        expected_samples.append((cutoff_day, target_day, row, values[target_day]))
    if len(expected_samples) != len(payload.training_samples):
        raise ValueError("NEM supervised samples do not match source observations")
    for (cutoff_day, target_day, expected_features, expected_target), supplied in zip(expected_samples, payload.training_samples):
        if supplied.cutoff_date != cutoff_day or supplied.target_date != target_day or not math.isclose(supplied.target, expected_target, rel_tol=1e-12):
            raise ValueError("NEM supervised target does not match source observations")
        if any(not math.isclose(supplied.features[name], expected_features[name], rel_tol=1e-12, abs_tol=1e-12) for name in NEM_FEATURE_NAMES):
            raise ValueError("NEM supervised features do not match prior observations")

    if payload.forecast is not None:
        cutoff = payload.forecast.cutoff_date
        feature_days = (cutoff, cutoff - timedelta(days=6), cutoff - timedelta(days=13), cutoff - timedelta(days=27))
        if any(day > cutoff for day in feature_days):
            raise ValueError("NEM forecast feature date exceeds cutoff_date")
        if any(day not in values for day in feature_days):
            raise ValueError("NEM forecast features are not ready for cutoff_date")
        expected_forecast = dict(zip(NEM_FEATURE_NAMES[:4], (values[day] for day in feature_days)))
        forecast_day = payload.forecast.forecast_date
        expected_forecast["day_of_week"] = float(forecast_day.weekday())
        expected_forecast["day_of_year"] = float(forecast_day.timetuple().tm_yday)
        if any(not math.isclose(payload.forecast.features[name], expected_forecast[name], rel_tol=1e-12, abs_tol=1e-12) for name in NEM_FEATURE_NAMES):
            raise ValueError("NEM forecast features do not match observations on or before cutoff_date")


def _labels(values: np.ndarray | list[float], threshold: float) -> list[str]:
    return ["Low" if float(value) <= threshold else "High" for value in values]


def _distribution(labels: list[str]) -> dict[str, int]:
    counts = Counter(labels)
    return {label: counts.get(label, 0) for label in LABELS}


def _classification_metrics(actual: list[str], predicted: list[str]) -> dict[str, Any]:
    return {
        "accuracy": round(float(accuracy_score(actual, predicted)), 6),
        "precision_high": round(float(precision_score(actual, predicted, pos_label=POSITIVE_LABEL, zero_division=0)), 6),
        "recall_high": round(float(recall_score(actual, predicted, pos_label=POSITIVE_LABEL, zero_division=0)), 6),
        "macro_f1": round(float(f1_score(actual, predicted, labels=list(LABELS), average="macro", zero_division=0)), 6),
        "confusion_matrix": {
            "labels": list(LABELS),
            "matrix": confusion_matrix(actual, predicted, labels=list(LABELS)).tolist(),
        },
    }


def _new_model() -> RandomForestClassifier:
    return RandomForestClassifier(**MODEL_PARAMETERS)


def _evaluate(payload: NEMPredictionRequest) -> dict[str, Any]:
    samples = payload.training_samples
    minimum = FOLD_COUNT * FOLD_SIZE + MIN_TRAINING_FOLD_SAMPLES
    if len(samples) < minimum:
        raise ValueError(f"At least {minimum} supervised samples are required for chronological classification; got {len(samples)}")
    x = np.asarray([[sample.features[name] for name in NEM_FEATURE_NAMES] for sample in samples], dtype=float)
    y = np.asarray([sample.target for sample in samples], dtype=float)
    # Embargo the validation day's C+1 label so training is available at cutoff C.
    splits = TimeSeriesSplit(n_splits=FOLD_COUNT, test_size=FOLD_SIZE, gap=1)
    folds = []
    pooled_actual: list[str] = []
    pooled_model: list[str] = []
    pooled_majority: list[str] = []

    for fold_number, (train_index, validation_index) in enumerate(splits.split(x), start=1):
        if len(train_index) < MIN_TRAINING_FOLD_SAMPLES:
            raise ValueError("chronological split produced an undersized training fold")
        y_train = y[train_index]
        y_validation = y[validation_index]
        threshold = float(median(y_train.tolist()))
        train_labels = _labels(y_train, threshold)
        validation_labels = _labels(y_validation, threshold)
        model = _new_model()
        model.fit(x[train_index], train_labels)
        predicted = model.predict(x[validation_index]).tolist()
        train_distribution = _distribution(train_labels)
        validation_distribution = _distribution(validation_labels)
        majority_label = max(LABELS, key=lambda label: (train_distribution[label], label == "Low"))
        majority_predictions = [majority_label] * len(validation_labels)
        validation_dates = [samples[int(index)].target_date for index in validation_index]
        notes = []
        if len([label for label, count in train_distribution.items() if count]) == 1:
            notes.append("training fold contains only one class; classifier cannot learn the absent class")
        if len([label for label, count in validation_distribution.items() if count]) == 1:
            notes.append("validation fold contains only one class; fold metrics have limited interpretation")
        folds.append({
            "fold": fold_number,
            "threshold_mw": threshold,
            "training_period": {
                "start": samples[int(train_index[0])].target_date.isoformat(),
                "end": samples[int(train_index[-1])].target_date.isoformat(),
                "sample_count": len(train_index),
            },
            "validation_period": {
                "start": validation_dates[0].isoformat(),
                "end": validation_dates[-1].isoformat(),
                "sample_count": len(validation_index),
            },
            "class_distribution": {
                "training": train_distribution,
                "validation": validation_distribution,
            },
            "majority_class": majority_label,
            "random_forest": _classification_metrics(validation_labels, predicted),
            "majority_class_baseline": _classification_metrics(validation_labels, majority_predictions),
            "limitations": notes,
        })
        pooled_actual.extend(validation_labels)
        pooled_model.extend(predicted)
        pooled_majority.extend(majority_predictions)

    return {
        "strategy": "TimeSeriesSplit chronological rolling-origin",
        "shuffle": False,
        "fold_count": len(folds),
        "folds": folds,
        "pooled_validation_metrics": {
            "random_forest": _classification_metrics(pooled_actual, pooled_model),
            "majority_class_baseline": _classification_metrics(pooled_actual, pooled_majority),
        },
        "pooled_validation_class_distribution": _distribution(pooled_actual),
        "metric_notes": {
            "precision_recall_positive_class": POSITIVE_LABEL,
            "macro_f1": "computed across Low and High with zero_division=0",
            "pooled_labels": "each fold applies its own training-only median threshold",
        },
    }


def train_nem_daily_classifier(payload: NEMPredictionRequest) -> dict[str, Any]:
    _ensure_h2_artifact_path_is_distinct()
    _validate_payload_features(payload)
    validation = _evaluate(payload)
    x = np.asarray([[sample.features[name] for name in NEM_FEATURE_NAMES] for sample in payload.training_samples], dtype=float)
    y = np.asarray([sample.target for sample in payload.training_samples], dtype=float)
    final_threshold = float(median(y.tolist()))
    final_labels = _labels(y, final_threshold)
    model = _new_model()
    model.fit(x, final_labels)

    path = nem_h2_artifact_path()
    trained_at = datetime.now(timezone.utc).isoformat()
    artifact = {
        "artifact_version": ARTIFACT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "horizon_days": NEM_FORECAST_HORIZON_DAYS,
        "feature_schema_version": NEM_FEATURE_SCHEMA_VERSION,
        "cutoff_target_contract": "Brisbane as_of_date - 1 cutoff; as_of_date + 1 target",
        "model": model,
        "model_name": MODEL_NAME,
        "sklearn_version": sklearn.__version__,
        "python_version": platform.python_version(),
        "trained_at": trained_at,
        "model_parameters": MODEL_PARAMETERS.copy(),
        "labels": list(LABELS),
        "positive_class": POSITIVE_LABEL,
        "threshold_mw": final_threshold,
        "feature_names": list(NEM_FEATURE_NAMES),
        "feature_units": NEM_FEATURE_UNITS.copy(),
        "dataset_id": payload.dataset_id,
        "dataset_name": payload.dataset_name,
        "dataset_source": payload.dataset_source,
        "network_code": payload.network_code,
        "metric": payload.metric,
        "interval": payload.interval,
        "unit": payload.unit,
        "training_start": payload.training_start.isoformat() if payload.training_start else None,
        "training_end": payload.training_end.isoformat() if payload.training_end else None,
        "training_sample_count": payload.training_sample_count,
        "observation_start": payload.observation_start.isoformat(),
        "observation_end": payload.observation_end.isoformat(),
        "observation_count": payload.observation_count,
        "training_data_fingerprint": payload.data_fingerprint,
        "validation": validation,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(prefix=path.name, suffix=".tmp", dir=path.parent, delete=False) as stream:
            temporary_name = stream.name
        joblib.dump(artifact, temporary_name)
        Path(temporary_name).replace(path)
    finally:
        if temporary_name and Path(temporary_name).exists():
            Path(temporary_name).unlink()

    return {
        "stage": "training",
        "dataset_id": payload.dataset_id,
        "dataset_name": payload.dataset_name,
        "dataset_source": payload.dataset_source,
        "model_name": MODEL_NAME,
        "target": "daily_demand_level",
        "network_code": "NEM",
        "interval": "1d",
        "forecast_horizon_days": NEM_FORECAST_HORIZON_DAYS,
        "feature_schema_version": NEM_FEATURE_SCHEMA_VERSION,
        "unit": "MW",
        "labels": list(LABELS),
        "threshold_mw": final_threshold,
        "threshold_rule": "Low if demand <= training median; High otherwise",
        "training_start": artifact["training_start"],
        "training_end": artifact["training_end"],
        "training_sample_count": payload.training_sample_count,
        "training_class_distribution": _distribution(final_labels),
        "training_data_fingerprint": payload.data_fingerprint,
        "validation": validation,
        "artifact_name": path.name,
        "model_provenance": {
            "model_type": "classification",
            "model_name": MODEL_NAME,
            "artifact_name": path.name,
            "artifact_format": "joblib",
            "artifact_version": artifact["artifact_version"],
            "contract_version": artifact["contract_version"],
            "horizon_days": artifact["horizon_days"],
            "feature_schema_version": artifact["feature_schema_version"],
            "python_version": artifact["python_version"],
            "sklearn_version": artifact["sklearn_version"],
            "trained_at": artifact["trained_at"],
            "model_parameters": artifact["model_parameters"],
        },
    }


def _load_artifact() -> tuple[dict[str, Any], Path]:
    # NEM fixed-horizon inference must use the matching H2 artifact. The H1
    # path remains separate and is never used as a fallback here.
    path = nem_h2_artifact_path()
    if not path.is_file():
        raise FileNotFoundError("NEM Classification artifact is missing")
    try:
        artifact = joblib.load(path)
    except Exception as exc:
        raise ValueError("NEM Classification artifact cannot be loaded") from exc
    expected = {
        "artifact_version": ARTIFACT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "model_name": MODEL_NAME,
        "labels": list(LABELS),
        "positive_class": POSITIVE_LABEL,
        "feature_names": list(NEM_FEATURE_NAMES),
        "feature_units": NEM_FEATURE_UNITS,
        "network_code": "NEM",
        "metric": "demand",
        "interval": "1d",
        "unit": "MW",
        "horizon_days": NEM_FORECAST_HORIZON_DAYS,
        "feature_schema_version": NEM_FEATURE_SCHEMA_VERSION,
        "cutoff_target_contract": "Brisbane as_of_date - 1 cutoff; as_of_date + 1 target",
    }
    if not isinstance(artifact, dict) or any(artifact.get(key) != value for key, value in expected.items()):
        raise ValueError("NEM Classification artifact is incompatible")
    if not isinstance(artifact.get("threshold_mw"), (int, float)) or not math.isfinite(artifact["threshold_mw"]):
        raise ValueError("NEM Classification artifact has an invalid threshold")
    if not hasattr(artifact.get("model"), "predict") or not hasattr(artifact.get("model"), "predict_proba"):
        raise ValueError("NEM Classification artifact is incompatible")
    return artifact, path


def classify_next_nem_day(payload: NEMPredictionRequest) -> dict[str, Any]:
    if payload.forecast_status != "ready" or payload.forecast is None:
        raise ValueError("NEM classification data is not ready")
    artifact, path = _load_artifact()
    identity = ("dataset_id", "dataset_name", "dataset_source", "network_code", "metric", "interval", "unit")
    if any(getattr(payload, key) != artifact.get(key) for key in identity):
        raise ValueError("NEM Classification artifact dataset identity does not match current data")
    _validate_payload_features(payload)
    feature_values = [payload.forecast.features[name] for name in NEM_FEATURE_NAMES]
    model = artifact["model"]
    label = str(model.predict([feature_values])[0])
    if label not in LABELS:
        raise ValueError("NEM Classification artifact returned an unknown label")
    probabilities_by_label = dict(zip(model.classes_, model.predict_proba([feature_values])[0]))
    probabilities = {name: round(float(probabilities_by_label.get(name, 0.0)), 6) for name in LABELS}
    if not all(math.isfinite(value) for value in probabilities.values()):
        raise ValueError("NEM Classification artifact returned invalid probabilities")
    return {
        "stage": "forecast",
        "forecast_status": "ready",
        "model_name": MODEL_NAME,
        "target": "daily_demand_level",
        "network_code": "NEM",
        "metric": "demand",
        "interval": "1d",
        "unit": "MW",
        "forecast_date": payload.forecast.forecast_date.isoformat(),
        "cutoff_date": payload.forecast.cutoff_date.isoformat(),
        "horizon_days": NEM_FORECAST_HORIZON_DAYS,
        "as_of_date": payload.forecast.as_of_date.isoformat(),
        "predicted_level": label,
        "probabilities": probabilities,
        "threshold_mw": float(artifact["threshold_mw"]),
        "threshold_rule": "Low if demand <= training median; High otherwise",
        "last_observed_date": payload.forecast.last_observed_date.isoformat(),
        "last_observed_at": payload.forecast.last_observed_at.isoformat(),
        "training_data_fingerprint": artifact["training_data_fingerprint"],
        "run_data_fingerprint": payload.data_fingerprint,
        "dataset_provenance": {
            "dataset_id": payload.dataset_id,
            "dataset_name": payload.dataset_name,
            "dataset_source": payload.dataset_source,
        },
        "artifact_name": path.name,
    }
