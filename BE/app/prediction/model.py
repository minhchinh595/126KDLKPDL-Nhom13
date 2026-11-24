import hashlib
import json
import os
from math import isfinite, sqrt
from pathlib import Path
from statistics import mean

import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error


WINDOW_MONTHS = 12


def _month_offset(month: str, offset: int) -> str:
    year, month_number = (int(part) for part in month.split("-"))
    absolute_month = year * 12 + month_number - 1 + offset
    result_year, result_month = divmod(absolute_month, 12)
    return f"{result_year:04d}-{result_month + 1:02d}"


def _artifact_path() -> Path:
    configured_path = os.getenv("PREDICTION_MODEL_PATH")
    if configured_path:
        return Path(configured_path)

    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / "artifacts" / "electricity_demand_rf.joblib"


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


def _make_model() -> RandomForestRegressor:
    return RandomForestRegressor(
        n_estimators=200,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=1,
    )


def _calculate_metrics(actual: list[float], predicted: list[float]) -> dict:
    errors = [prediction - truth for truth, prediction in zip(actual, predicted)]
    nonzero_actual = [
        (truth, prediction)
        for truth, prediction in zip(actual, predicted)
        if truth != 0
    ]

    mape = (
        mean(
            abs(prediction - truth) / abs(truth)
            for truth, prediction in nonzero_actual
        ) * 100
        if nonzero_actual
        else None
    )

    return {
        "mae": round(float(mean_absolute_error(actual, predicted)), 4),
        "rmse": round(float(sqrt(mean(error ** 2 for error in errors))), 4),
        "mape_pct": round(float(mape), 4) if mape is not None else None,
        "r2": round(float(r2_score(actual, predicted)), 6),
    }


def train_and_save_model(records: list[dict]) -> dict:
    """Evaluate chronologically, fit on all data, and save the final model."""
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

    evaluation_model = _make_model()
    evaluation_model.fit(train_x, train_y)
    model_predictions = [
        float(value) for value in evaluation_model.predict(test_x)
    ]

    # The oldest input in each 12-month window is the same month one year earlier.
    seasonal_naive_predictions = [row[0] for row in test_x]

    final_model = _make_model()
    final_model.fit(features, targets)

    latest_month = max(values_by_month)
    artifact = {
        "model": final_model,
        "window_months": WINDOW_MONTHS,
        "trained_through_month": latest_month,
        "data_fingerprint": _data_fingerprint(values_by_month),
        "feature_names": [
            f"demand_lag_{lag}"
            for lag in reversed(range(1, WINDOW_MONTHS + 1))
        ],
    }

    model_path = _artifact_path()
    model_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = model_path.with_name(model_path.name + ".tmp")
    joblib.dump(artifact, temporary_path)
    temporary_path.replace(model_path)

    return {
        "stage": "training",
        "model_name": "RandomForestRegressor",
        "window_months": WINDOW_MONTHS,
        "trained_through_month": latest_month,
        "training_sample_count": len(features),
        "holdout_sample_count": len(test_x),
        "holdout_start_month": test_months[0],
        "holdout_end_month": test_months[-1],
        "holdout_metrics": _calculate_metrics(test_y, model_predictions),
        "seasonal_naive_metrics": _calculate_metrics(
            test_y,
            seasonal_naive_predictions,
        ),
        "artifact_name": model_path.name,
    }


def forecast_next_month(records: list[dict]) -> dict:
    """Load the saved model and forecast the month after the latest data."""
    values_by_month = _normalize_records(records)
    if not values_by_month:
        raise ValueError("No demand records are available")

    model_path = _artifact_path()
    if not model_path.is_file():
        raise FileNotFoundError(
            "Prediction model is not trained. Call POST /api/prediction/train first."
        )

    try:
        artifact = joblib.load(model_path)
    except Exception as exc:
        raise ValueError("Prediction model artifact cannot be loaded. Train the prediction model again.") from exc
    if not isinstance(artifact, dict) or not all(
        key in artifact for key in ("model", "window_months", "trained_through_month", "feature_names", "data_fingerprint")
    ):
        raise ValueError("Prediction model artifact is incomplete or incompatible. Train the prediction model again.")
    if artifact.get("window_months") != WINDOW_MONTHS:
        raise ValueError("Prediction model artifact uses an incompatible input window. Train the prediction model again.")
    latest_month = max(values_by_month)

    if latest_month != artifact.get("trained_through_month"):
        raise ValueError(
            "Prediction model is stale. The latest database month is "
            f"{latest_month}, but the model was trained through "
            f"{artifact.get('trained_through_month')}. Train the model again."
        )
    if _data_fingerprint(values_by_month) != artifact.get("data_fingerprint"):
        raise ValueError("Prediction model was built from different source data. Train the model again.")

    forecast_month = _month_offset(latest_month, 1)
    input_months = [
        _month_offset(forecast_month, -offset)
        for offset in reversed(range(1, WINDOW_MONTHS + 1))
    ]

    if not all(month in values_by_month for month in input_months):
        raise ValueError(
            "The latest 12 consecutive months are required for forecasting"
        )

    input_values = [values_by_month[month] for month in input_months]
    prediction = float(artifact["model"].predict([input_values])[0])

    if not isfinite(prediction):
        raise ValueError("The model returned an invalid prediction")

    return {
        "stage": "forecast",
        "model_name": "RandomForestRegressor",
        "forecast_month": forecast_month,
        "predicted_demand": round(max(0.0, prediction), 4),
        "unit": "TWh",
        "trained_through_month": latest_month,
        "window_months": WINDOW_MONTHS,
        "artifact_name": model_path.name,
    }
