import json

import pytest

from app.clients.prediction import PredictionServiceClient
from app.clients.prediction import PredictionServiceUnavailable


SECRET = "nem-prediction-client-test-secret-at-least-32-bytes"


class Response:
    status = 200

    payload = {
        "stage": "forecast", "model_name": "RandomForestRegressor", "target": "daily_demand",
        "network_code": "NEM", "metric": "demand", "interval": "1d",
        "forecast_status": "ready", "as_of_date": "2026-11-26", "cutoff_date": "2026-11-25",
        "forecast_date": "2026-11-27", "horizon_days": 2,
        "predicted_demand": 18000.0, "unit": "MW",
        "last_observed_date": "2026-11-25", "last_observed_at": "2026-11-25T00:00:00+10:00",
        "training_data_fingerprint": "a" * 64, "run_data_fingerprint": "b" * 64,
        "artifact_name": "electricity_nem_daily_demand_rf_h2.joblib",
        "dataset_provenance": {
            "dataset_id": 1, "dataset_name": "Open Electricity NEM",
            "dataset_source": "https://api.openelectricity.org.au/v4/market/network/NEM",
            "network_code": "NEM", "metric": "demand", "interval": "1d", "unit": "MW",
        },
    }

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_prediction_client_posts_nem_payload_to_dedicated_internal_endpoint():
    captured = []
    body = {"network_code": "NEM", "interval": "1d", "forecast": {
        "as_of_date": "2026-11-26", "cutoff_date": "2026-11-25", "forecast_date": "2026-11-27",
    }}

    def opener(request, timeout):
        captured.append((request.full_url, json.loads(request.data), timeout))
        return Response()

    client = PredictionServiceClient(
        base_url="http://prediction:8103",
        secret=SECRET,
        timeout_seconds=42,
        opener=opener,
    )
    result = client.run_nem(body)
    assert result == Response.payload
    assert result["dataset_provenance"] == {
        "dataset_id": 1,
        "dataset_name": "Open Electricity NEM",
        "dataset_source": "https://api.openelectricity.org.au/v4/market/network/NEM",
        "network_code": "NEM",
        "metric": "demand",
        "interval": "1d",
        "unit": "MW",
    }
    assert captured == [("http://prediction:8103/internal/prediction/nem/run", body, 42)]


def _valid_training_response():
    metrics = {"mae_mw": 100.0, "rmse_mw": 120.0, "mape_pct": 1.0}
    return {
        "stage": "training",
        "model_name": "RandomForestRegressor",
        "target": "daily_demand",
        "unit": "MW",
        "network_code": "NEM",
        "metric": "demand",
        "interval": "1d",
        "forecast_horizon_days": 2,
        "feature_schema_version": "nem_daily_demand_h2_v1",
        "dataset_id": 4,
        "dataset_name": "Open Electricity NEM",
        "dataset_source": "https://api.openelectricity.org.au/v4/market/network/NEM",
        "observation_start": "2025-11-26",
        "observation_end": "2026-11-25",
        "training_start": "2025-12-01",
        "training_end": "2026-11-23",
        "training_sample_count": 300,
        "training_data_fingerprint": "a" * 64,
        "feature_names": ["demand_lag_1", "demand_lag_7"],
        "validation": {
            "shuffle": False,
            "fold_count": 1,
            "folds": [{
                "validation_sample_count": 10,
                "random_forest": metrics,
                "persistence_baseline": metrics,
                "seasonal_naive_7d_baseline": metrics,
            }],
            "overall": {
                "random_forest": metrics,
                "persistence_baseline": metrics,
                "seasonal_naive_7d_baseline": metrics,
            },
        },
        "artifact_name": "electricity_nem_daily_demand_rf_h2.joblib",
    }


def test_prediction_train_response_requires_observation_range_fields():
    class TrainingResponse(Response):
        payload = _valid_training_response()

    client = PredictionServiceClient(
        base_url="http://prediction:8103",
        secret=SECRET,
        opener=lambda *_args, **_kwargs: TrainingResponse(),
    )
    assert client.train_nem({"training_samples": []})["observation_end"] == "2026-11-25"

    class MissingObservationStartResponse(TrainingResponse):
        payload = _valid_training_response()
        payload.pop("observation_start")

    client = PredictionServiceClient(
        base_url="http://prediction:8103",
        secret=SECRET,
        opener=lambda *_args, **_kwargs: MissingObservationStartResponse(),
    )
    with pytest.raises(PredictionServiceUnavailable, match="incompatible response"):
        client.train_nem({"training_samples": []})


@pytest.mark.parametrize(
    "provenance_change",
    [
        None,
        {"dataset_source": "https://example.invalid/other"},
        {"network_code": "NSW1"},
    ],
)
def test_prediction_client_rejects_missing_or_incompatible_nem_provenance(provenance_change):
    payload = dict(Response.payload)
    if provenance_change is None:
        payload.pop("dataset_provenance")
    else:
        payload["dataset_provenance"] = {
            **Response.payload["dataset_provenance"],
            **provenance_change,
        }

    class InvalidProvenanceResponse(Response):
        pass

    InvalidProvenanceResponse.payload = payload
    client = PredictionServiceClient(
        base_url="http://prediction:8103",
        secret=SECRET,
        opener=lambda *_args, **_kwargs: InvalidProvenanceResponse(),
    )

    with pytest.raises(PredictionServiceUnavailable, match="incompatible response"):
        client.run_nem({"network_code": "NEM", "interval": "1d", "forecast": {
            "as_of_date": "2026-11-26", "cutoff_date": "2026-11-25", "forecast_date": "2026-11-27",
        }})


@pytest.mark.parametrize("artifact_name", [
    "electricity_nem_daily_demand_rf.joblib",
    None,
    "electricity_nem_daily_demand_classifier_h2.joblib",
])
def test_prediction_client_rejects_missing_or_non_h2_artifact_identity(artifact_name):
    payload = {**Response.payload}
    if artifact_name is None:
        payload.pop("artifact_name")
    else:
        payload["artifact_name"] = artifact_name

    class WrongArtifactResponse(Response):
        pass

    WrongArtifactResponse.payload = payload
    client = PredictionServiceClient(
        base_url="http://prediction:8103",
        secret=SECRET,
        opener=lambda *_args, **_kwargs: WrongArtifactResponse(),
    )
    with pytest.raises(PredictionServiceUnavailable, match="incompatible response"):
        client.run_nem({"network_code": "NEM", "interval": "1d", "forecast": {
            "as_of_date": "2026-11-26", "cutoff_date": "2026-11-25", "forecast_date": "2026-11-27",
        }})


def test_prediction_client_rejects_forecast_date_different_from_request():
    class MismatchedDateResponse(Response):
        payload = {
            **Response.payload,
            "as_of_date": "2026-11-27",
            "cutoff_date": "2026-11-26",
            "forecast_date": "2026-11-28",
            "last_observed_date": "2026-11-26",
            "last_observed_at": "2026-11-26T00:00:00+10:00",
        }

    client = PredictionServiceClient(
        base_url="http://prediction:8103",
        secret=SECRET,
        opener=lambda *_args, **_kwargs: MismatchedDateResponse(),
    )
    with pytest.raises(PredictionServiceUnavailable, match="dates inconsistent with the request"):
        client.run_nem({"network_code": "NEM", "interval": "1d", "forecast": {
            "as_of_date": "2026-11-26", "cutoff_date": "2026-11-25", "forecast_date": "2026-11-27",
        }})
