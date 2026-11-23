from pathlib import Path

import pytest

from scripts.import_electricity_data import load_rows


@pytest.fixture
def monthly_records():
    csv_path = Path(__file__).resolve().parents[2] / "data" / "processed" / "vietnam_electricity_demand.csv"
    return [{"month": row["month"].strftime("%Y-%m"), "value": float(row["value"])} for row in load_rows(csv_path)]


def test_clustering_run_loads_saved_artifact_without_fitting(tmp_path, monkeypatch, monthly_records):
    from app.clustering import kmeans

    artifact = tmp_path / "clustering.joblib"
    monkeypatch.setattr(kmeans, "artifact_path", lambda: artifact)
    trained = kmeans.train_and_save_model(monthly_records)
    assert trained["stage"] == "training"
    assert artifact.is_file()

    def unexpected_fit(*args, **kwargs):
        raise AssertionError("run must not fit a scaler or clustering model")

    monkeypatch.setattr(kmeans.StandardScaler, "fit", unexpected_fit)
    monkeypatch.setattr(kmeans.StandardScaler, "fit_transform", unexpected_fit)
    monkeypatch.setattr(kmeans.KMeans, "fit", unexpected_fit)
    monkeypatch.setattr(kmeans.KMeans, "fit_predict", unexpected_fit)
    result = kmeans.build_clustering_result(monthly_records)
    assert result["stage"] == "run"
    assert result["trained_through_month"] == "2026-09"
    assert result["assignments"]
    changed_records = [*monthly_records]
    changed_records[-1] = {**changed_records[-1], "value": changed_records[-1]["value"] + 0.1}
    with pytest.raises(ValueError, match="different source data"):
        kmeans.build_clustering_result(changed_records)


@pytest.mark.parametrize("module_name,train_name,run_name,artifact_name", [
    ("app.prediction.model", "train_and_save_model", "forecast_next_month", "prediction.joblib"),
    ("app.classification.model", "train_and_save_model", "classify_next_month", "classification.joblib"),
])
def test_forecast_models_run_from_artifact_without_refitting(tmp_path, monkeypatch, monthly_records, module_name, train_name, run_name, artifact_name):
    import importlib

    module = importlib.import_module(module_name)
    artifact = tmp_path / artifact_name
    monkeypatch.setattr(module, "_artifact_path", lambda: artifact)
    training_result = getattr(module, train_name)(monthly_records)
    assert training_result["stage"] == "training"
    assert artifact.is_file()

    def unexpected_fit(*args, **kwargs):
        raise AssertionError("run must not fit a new model")

    monkeypatch.setattr(module, "_make_model", unexpected_fit)
    result = getattr(module, run_name)(monthly_records)
    assert result["stage"] == "forecast"
    assert result["forecast_month"] == "2026-10"
    changed_records = [*monthly_records]
    changed_records[-1] = {**changed_records[-1], "value": changed_records[-1]["value"] + 0.1}
    with pytest.raises(ValueError, match="different source data"):
        getattr(module, run_name)(changed_records)
