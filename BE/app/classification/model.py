import hashlib
import json
import os
from math import isfinite
from pathlib import Path
from statistics import mean

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)


WINDOW_MONTHS = 12
LABELS = ("low", "medium", "high")
LABEL_NAMES = {
    "low": "Nhu cầu thấp",
    "medium": "Nhu cầu trung bình",
    "high": "Nhu cầu cao",
}


def _month_offset(month: str, offset: int) -> str:
    year, month_number = (int(part) for part in month.split("-"))
    absolute_month = year * 12 + month_number - 1 + offset
    result_year, result_month = divmod(absolute_month, 12)
    return f"{result_year:04d}-{result_month + 1:02d}"


def _artifact_path() -> Path:
    configured_path = os.getenv("CLASSIFICATION_MODEL_PATH")
    if configured_path:
        return Path(configured_path)

    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / "artifacts" / "electricity_demand_classifier.joblib"


def _normalize_records(records: list[dict]) -> dict[str, float]:
    values_by_month: dict[str, float] = {}

    for record in records:
        month = record["month"]
        value = float(record["value"])

        if month in values_by_month:
            raise ValueError(f"Duplicate month in dataset: {month}")
        if not isfinite(value) or value < 0:
            raise ValueError(f"Invalid demand value for {month}")

        values_by_month[month] = value

    return values_by_month


def _data_fingerprint(values_by_month: dict[str, float]) -> str:
    payload = sorted(values_by_month.items())
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def _build_training_samples(
    values_by_month: dict[str, float],
) -> tuple[list[list[float]], list[float], list[str]]:
    features = []
    targets = []
    target_months = []

    for target_month in sorted(values_by_month):
        input_months = [
            _month_offset(target_month, -offset)
            for offset in reversed(range(1, WINDOW_MONTHS + 1))
        ]

        if not all(month in values_by_month for month in input_months):
            continue

        features.append([values_by_month[month] for month in input_months])
        targets.append(values_by_month[target_month])
        target_months.append(target_month)

    return features, targets, target_months


def _get_thresholds(targets: list[float]) -> tuple[float, float]:
    if len(targets) < 3:
        raise ValueError("At least three target values are required for classification")

    q33, q67 = np.quantile(targets, [1 / 3, 2 / 3])

    if not float(q33) < float(q67):
        raise ValueError(
            "The training data cannot form three distinct demand levels "
            "using the 33% and 67% quantiles"
        )

    return float(q33), float(q67)


def _label_values(
    values: list[float],
    q33: float,
    q67: float,
) -> list[str]:
    labels = []

    for value in values:
        if value <= q33:
            labels.append("low")
        elif value <= q67:
            labels.append("medium")
        else:
            labels.append("high")

    return labels


def _make_model() -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=300,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
        n_jobs=1,
    )


def _calculate_metrics(actual: list[str], predicted: list[str]) -> dict:
    report = classification_report(
        actual,
        predicted,
        labels=list(LABELS),
        target_names=[LABEL_NAMES[label] for label in LABELS],
        output_dict=True,
        zero_division=0,
    )

    per_class = {}
    for label in LABELS:
        class_report = report[LABEL_NAMES[label]]
        per_class[label] = {
            "precision": round(float(class_report["precision"]), 4),
            "recall": round(float(class_report["recall"]), 4),
            "f1_score": round(float(class_report["f1-score"]), 4),
            "support": int(class_report["support"]),
        }

    matrix = confusion_matrix(
        actual,
        predicted,
        labels=list(LABELS),
    ).tolist()

    return {
        "accuracy": round(float(accuracy_score(actual, predicted)), 4),
        "macro_f1": round(float(f1_score(
            actual,
            predicted,
            labels=list(LABELS),
            average="macro",
            zero_division=0,
        )), 4),
        "per_class": per_class,
        "confusion_matrix": {
            "labels": list(LABELS),
            "label_names": [LABEL_NAMES[label] for label in LABELS],
            "matrix": matrix,
        },
    }


def train_and_save_model(records: list[dict]) -> dict:
    """Evaluate chronologically, fit on all data, and save the final classifier."""
    values_by_month = _normalize_records(records)
    features, targets, target_months = _build_training_samples(values_by_month)

    if len(features) < 15:
        raise ValueError(
            "At least 15 complete 12-month training samples are required"
        )

    holdout_size = min(12, max(3, len(features) // 5))
    split_index = len(features) - holdout_size

    train_x = features[:split_index]
    train_y = targets[:split_index]
    test_x = features[split_index:]
    test_y = targets[split_index:]
    test_months = target_months[split_index:]

    # Use only the training portion to define thresholds for evaluation.
    evaluation_q33, evaluation_q67 = _get_thresholds(train_y)
    train_labels = _label_values(train_y, evaluation_q33, evaluation_q67)
    test_labels = _label_values(test_y, evaluation_q33, evaluation_q67)

    if set(train_labels) != set(LABELS):
        raise ValueError(
            "The chronological training partition does not contain all three "
            "demand levels"
        )

    evaluation_model = _make_model()
    evaluation_model.fit(train_x, train_labels)
    model_predictions = evaluation_model.predict(test_x).tolist()
    evaluation_metrics = _calculate_metrics(test_labels, model_predictions)

    majority_label = max(
        LABELS,
        key=lambda label: train_labels.count(label),
    )
    baseline_predictions = [majority_label] * len(test_labels)
    baseline_metrics = _calculate_metrics(test_labels, baseline_predictions)

    # Recalculate thresholds and fit the deployed model on all available history.
    final_q33, final_q67 = _get_thresholds(targets)
    final_labels = _label_values(targets, final_q33, final_q67)

    if set(final_labels) != set(LABELS):
        raise ValueError(
            "The complete dataset does not contain all three demand levels"
        )

    final_model = _make_model()
    final_model.fit(features, final_labels)

    latest_month = max(values_by_month)
    artifact = {
        "model": final_model,
        "window_months": WINDOW_MONTHS,
        "trained_through_month": latest_month,
        "data_fingerprint": _data_fingerprint(values_by_month),
        "q33_twh": final_q33,
        "q67_twh": final_q67,
        "labels": list(LABELS),
        "label_names": LABEL_NAMES,
    }

    model_path = _artifact_path()
    model_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = model_path.with_name(model_path.name + ".tmp")
    joblib.dump(artifact, temporary_path)
    temporary_path.replace(model_path)

    return {
        "stage": "training",
        "model_name": "RandomForestClassifier",
        "window_months": WINDOW_MONTHS,
        "trained_through_month": latest_month,
        "training_sample_count": len(features),
        "holdout_sample_count": len(test_x),
        "holdout_start_month": test_months[0],
        "holdout_end_month": test_months[-1],
        "evaluation_thresholds": {
            "q33_twh": round(evaluation_q33, 4),
            "q67_twh": round(evaluation_q67, 4),
        },
        "final_thresholds": {
            "q33_twh": round(final_q33, 4),
            "q67_twh": round(final_q67, 4),
            "rules": {
                "low": f"value <= {round(final_q33, 4)} TWh",
                "medium": (
                    f"{round(final_q33, 4)} < value <= "
                    f"{round(final_q67, 4)} TWh"
                ),
                "high": f"value > {round(final_q67, 4)} TWh",
            },
        },
        "holdout_metrics": evaluation_metrics,
        "majority_class_baseline_metrics": baseline_metrics,
        "artifact_name": model_path.name,
    }


def classify_next_month(records: list[dict]) -> dict:
    """Load the saved classifier and classify the month after available data."""
    values_by_month = _normalize_records(records)
    if not values_by_month:
        raise ValueError("No demand records are available")

    model_path = _artifact_path()
    if not model_path.is_file():
        raise FileNotFoundError(
            "Classification model is not trained. "
            "Call POST /api/classification/train first."
        )

    try:
        artifact = joblib.load(model_path)
    except Exception as exc:
        raise ValueError("Classification model artifact cannot be loaded. Train the classification model again.") from exc
    if not isinstance(artifact, dict) or not all(
        key in artifact for key in ("model", "window_months", "trained_through_month", "data_fingerprint", "q33_twh", "q67_twh", "labels", "label_names")
    ):
        raise ValueError("Classification model artifact is incomplete or incompatible. Train the classification model again.")
    if artifact.get("window_months") != WINDOW_MONTHS or tuple(artifact.get("labels", ())) != LABELS:
        raise ValueError("Classification model artifact uses an incompatible format. Train the classification model again.")
    latest_month = max(values_by_month)

    if latest_month != artifact.get("trained_through_month"):
        raise ValueError(
            "Classification model is stale. The latest database month is "
            f"{latest_month}, but the model was trained through "
            f"{artifact.get('trained_through_month')}. Train the model again."
        )
    if _data_fingerprint(values_by_month) != artifact.get("data_fingerprint"):
        raise ValueError("Classification model was built from different source data. Train the model again.")

    forecast_month = _month_offset(latest_month, 1)
    input_months = [
        _month_offset(forecast_month, -offset)
        for offset in reversed(range(1, WINDOW_MONTHS + 1))
    ]

    if not all(month in values_by_month for month in input_months):
        raise ValueError(
            "The latest 12 consecutive months are required for classification"
        )

    input_values = [
        values_by_month[month]
        for month in input_months
    ]

    model = artifact["model"]
    predicted_label = str(model.predict([input_values])[0])
    class_probabilities = model.predict_proba([input_values])[0]

    probabilities = [
        {
            "label": str(label),
            "label_name": LABEL_NAMES[str(label)],
            "probability": round(float(probability), 6),
        }
        for label, probability in zip(model.classes_, class_probabilities)
    ]

    return {
        "stage": "forecast",
        "model_name": "RandomForestClassifier",
        "forecast_month": forecast_month,
        "predicted_level": predicted_label,
        "predicted_level_name": LABEL_NAMES[predicted_label],
        "probabilities": probabilities,
        "thresholds": {
            "q33_twh": round(float(artifact["q33_twh"]), 4),
            "q67_twh": round(float(artifact["q67_twh"]), 4),
        },
        "trained_through_month": latest_month,
        "window_months": WINDOW_MONTHS,
        "artifact_name": model_path.name,
    }
