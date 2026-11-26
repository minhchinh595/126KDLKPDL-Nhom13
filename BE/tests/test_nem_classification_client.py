import json
import pytest

from app.clients.classification import ClassificationServiceClient, ClassificationServiceUnavailable


SECRET = "nem-classification-client-test-secret-at-least-32-bytes"


class Response:
    status = 200

    payload = {
        "stage": "forecast", "model_name": "RandomForestClassifier",
        "target": "daily_demand_level", "network_code": "NEM", "metric": "demand",
        "interval": "1d", "unit": "MW", "forecast_status": "ready", "horizon_days": 2,
        "as_of_date": "2026-11-26", "cutoff_date": "2026-11-25", "forecast_date": "2026-11-27",
        "last_observed_date": "2026-11-25", "last_observed_at": "2026-11-25T00:00:00+10:00",
        "predicted_level": "High", "probabilities": {"Low": 0.2, "High": 0.8},
        "threshold_mw": 17000,
        "dataset_provenance": {
            "dataset_name": "Open Electricity NEM",
            "dataset_source": "https://api.openelectricity.org.au/v4/market/network/NEM",
        },
        "artifact_name": "electricity_nem_daily_demand_classifier_h2.joblib",
    }

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_client_calls_nem_internal_route_with_normalized_payload():
    body = {"network_code": "NEM", "metric": "demand", "interval": "1d", "unit": "MW",
            "forecast": {"as_of_date": "2026-11-26", "cutoff_date": "2026-11-25", "forecast_date": "2026-11-27"}}
    captured = []

    def opener(request, timeout):
        captured.append((request.full_url, request.get_header("X-classification-service-secret"), json.loads(request.data), timeout))
        return Response()

    client = ClassificationServiceClient(
        base_url="http://classification:8104/",
        secret=SECRET,
        timeout_seconds=25,
        opener=opener,
    )
    assert client.run_nem(body) == Response.payload
    assert captured == [
        (
            "http://classification:8104/internal/classification/nem/run",
            SECRET,
            body,
            25,
        )
    ]


@pytest.mark.parametrize("artifact_name", [
    "electricity_nem_daily_demand_classifier.joblib",
    None,
    "electricity_nem_daily_demand_rf_h2.joblib",
])
def test_client_rejects_missing_or_non_h2_artifact_identity(artifact_name):
    payload = {**Response.payload}
    if artifact_name is None:
        payload.pop("artifact_name")
    else:
        payload["artifact_name"] = artifact_name

    class WrongArtifactResponse(Response):
        pass

    WrongArtifactResponse.payload = payload
    client = ClassificationServiceClient(
        base_url="http://classification:8104",
        secret=SECRET,
        timeout_seconds=25,
        opener=lambda *_args, **_kwargs: WrongArtifactResponse(),
    )
    body = {"forecast": {
        "as_of_date": "2026-11-26", "cutoff_date": "2026-11-25", "forecast_date": "2026-11-27",
    }}
    with pytest.raises(ClassificationServiceUnavailable, match="incompatible response"):
        client.run_nem(body)


def test_client_rejects_classification_for_a_different_target_date():
    class MismatchedDateResponse(Response):
        payload = {
            **Response.payload,
            "as_of_date": "2026-11-27",
            "cutoff_date": "2026-11-26",
            "forecast_date": "2026-11-28",
            "last_observed_date": "2026-11-26",
            "last_observed_at": "2026-11-26T00:00:00+10:00",
        }

    client = ClassificationServiceClient(
        base_url="http://classification:8104",
        secret=SECRET,
        timeout_seconds=25,
        opener=lambda *_args, **_kwargs: MismatchedDateResponse(),
    )
    body = {"forecast": {
        "as_of_date": "2026-11-26", "cutoff_date": "2026-11-25", "forecast_date": "2026-11-27",
    }}

    with pytest.raises(ClassificationServiceUnavailable, match="dates inconsistent"):
        client.run_nem(body)


@pytest.mark.parametrize("probabilities", [
    {"Low": 0.8893, "High": 0.1107},
    {"Low": 1.0, "High": 0.0},
    {"Low": 0.0, "High": 1.0},
])
def test_client_accepts_finite_class_probabilities_summing_to_one(probabilities):
    class ValidProbabilityResponse(Response):
        payload = {**Response.payload, "probabilities": probabilities}

    client = ClassificationServiceClient(
        base_url="http://classification:8104",
        secret=SECRET,
        timeout_seconds=25,
        opener=lambda *_args, **_kwargs: ValidProbabilityResponse(),
    )
    body = {"forecast": {
        "as_of_date": "2026-11-26", "cutoff_date": "2026-11-25", "forecast_date": "2026-11-27",
    }}

    assert client.run_nem(body)["probabilities"] == probabilities


@pytest.mark.parametrize("probabilities", [
    {"Low": 0.8, "High": 0.3},
    {"Low": 0.8, "High": 0.1},
    {"Low": -0.1, "High": 1.1},
    {"Low": float("nan"), "High": 1.0},
    {"Low": 0.5, "High": float("inf")},
    {"Low": 0.8},
    {"High": 0.2},
])
def test_client_rejects_malformed_class_probabilities(probabilities):
    class InvalidProbabilityResponse(Response):
        payload = {**Response.payload, "probabilities": probabilities}

    client = ClassificationServiceClient(
        base_url="http://classification:8104",
        secret=SECRET,
        timeout_seconds=25,
        opener=lambda *_args, **_kwargs: InvalidProbabilityResponse(),
    )
    body = {"forecast": {
        "as_of_date": "2026-11-26", "cutoff_date": "2026-11-25", "forecast_date": "2026-11-27",
    }}

    with pytest.raises(ClassificationServiceUnavailable, match="incompatible response"):
        client.run_nem(body)
