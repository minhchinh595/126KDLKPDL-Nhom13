import json
import logging
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from app.clients.prediction import (
    PredictionArtifactWriteError,
    PredictionServiceClient,
    PredictionServiceConflict,
    PredictionServiceRejected,
    PredictionServiceUnavailable,
    prediction_diagnostic_context,
)


SECRET = "prediction-test-secret-with-at-least-32-bytes"
RECORDS = [{"month": "2026-08", "value": 28.5}, {"month": "2026-09", "value": 30.3}]


def _legacy_metrics():
    return {"mae": 1.0, "rmse": 1.2, "mape_pct": 3.4, "r2": 0.8}


def _legacy_train_response():
    return {
        "stage": "training", "model_name": "RandomForestRegressor", "window_months": 12,
        "trained_through_month": "2026-09", "training_sample_count": 20,
        "holdout_sample_count": 4, "holdout_start_month": "2026-06",
        "holdout_end_month": "2026-09", "holdout_metrics": _legacy_metrics(),
        "seasonal_naive_metrics": _legacy_metrics(), "artifact_name": "model.joblib",
    }


def _legacy_forecast_response():
    return {
        "stage": "forecast", "model_name": "RandomForestRegressor", "forecast_month": "2026-10",
        "predicted_demand": 30.1, "unit": "TWh", "trained_through_month": "2026-09",
        "window_months": 12, "artifact_name": "model.joblib",
    }


def _nem_metrics():
    return {"mae_mw": 10.0, "rmse_mw": 12.0, "mape_pct": 2.5}


def _nem_train_response():
    fold = {
        "validation_sample_count": 28,
        "random_forest": _nem_metrics(),
        "persistence_baseline": _nem_metrics(),
        "seasonal_naive_7d_baseline": _nem_metrics(),
    }
    return {
        "stage": "training", "model_name": "RandomForestRegressor", "target": "daily_demand",
        "unit": "MW", "network_code": "NEM", "metric": "demand", "interval": "1d",
        "forecast_horizon_days": 2, "feature_schema_version": "nem_daily_demand_h2_v1",
        "dataset_id": 1, "dataset_name": "Open Electricity NEM",
        "dataset_source": "https://api.openelectricity.org.au/v4/market/network/NEM",
        "observation_start": "2025-11-26", "observation_end": "2026-11-25",
        "training_start": "2025-12-25", "training_end": "2026-11-25",
        "feature_names": ["demand_at_cutoff", "demand_6d_before_cutoff", "demand_13d_before_cutoff", "demand_27d_before_cutoff", "day_of_week", "day_of_year"],
        "training_sample_count": 336, "training_data_fingerprint": "a" * 64,
        "validation": {
            "shuffle": False, "fold_count": 1, "folds": [fold],
            "overall": {
                "random_forest": _nem_metrics(), "persistence_baseline": _nem_metrics(),
                "seasonal_naive_7d_baseline": _nem_metrics(),
            },
        },
        "artifact_name": "electricity_nem_daily_demand_rf_h2.joblib",
    }


def _nem_forecast_response():
    return {
        "stage": "forecast", "model_name": "RandomForestRegressor", "target": "daily_demand",
        "network_code": "NEM", "metric": "demand", "interval": "1d",
        "forecast_status": "ready", "as_of_date": "2026-11-26", "cutoff_date": "2026-11-25",
        "horizon_days": 2, "forecast_date": "2026-11-27",
        "predicted_demand": 18000.0, "unit": "MW",
        "last_observed_date": "2026-11-25",
        "last_observed_at": "2026-11-25T00:00:00+10:00", "training_data_fingerprint": "a" * 64,
        "run_data_fingerprint": "b" * 64, "artifact_name": "electricity_nem_daily_demand_rf_h2.joblib",
        "dataset_provenance": {
            "dataset_id": 1, "dataset_name": "Open Electricity NEM",
            "dataset_source": "https://api.openelectricity.org.au/v4/market/network/NEM",
            "network_code": "NEM", "metric": "demand", "interval": "1d", "unit": "MW",
        },
    }


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def test_prediction_client_posts_train_and_run_with_secret_timeout_and_payload():
    captured = []
    responses = iter([FakeResponse(_legacy_train_response()), FakeResponse(_legacy_forecast_response())])

    def opener(request, timeout):
        captured.append({
            "url": request.full_url,
            "secret": request.get_header("X-prediction-service-secret"),
            "payload": json.loads(request.data),
            "timeout": timeout,
        })
        return next(responses)

    client = PredictionServiceClient(
        base_url="http://prediction.internal:8103/",
        secret=SECRET,
        timeout_seconds=120,
        opener=opener,
    )
    assert client.train(RECORDS) == _legacy_train_response()
    assert client.run(RECORDS) == _legacy_forecast_response()
    assert captured == [
        {
            "url": "http://prediction.internal:8103/internal/prediction/train",
            "secret": SECRET,
            "payload": {"records": RECORDS},
            "timeout": 120,
        },
        {
            "url": "http://prediction.internal:8103/internal/prediction/run",
            "secret": SECRET,
            "payload": {"records": RECORDS},
            "timeout": 120,
        },
    ]


@pytest.mark.parametrize(
    "status,error_type",
    [
        (409, PredictionServiceConflict),
        (422, PredictionServiceRejected),
        (503, PredictionServiceUnavailable),
        (507, PredictionArtifactWriteError),
    ],
)
def test_prediction_client_maps_errors_without_leaking_internal_details(status, error_type):
    def opener(request, timeout):
        raise HTTPError(request.full_url, status, "failed", None, BytesIO(b"private path and secret"))

    client = PredictionServiceClient(base_url="http://hidden:8103", secret=SECRET, opener=opener)
    with pytest.raises(error_type) as error:
        client.run(RECORDS)
    assert "private path" not in str(error.value)
    assert "hidden" not in str(error.value)
    assert SECRET not in str(error.value)


def test_prediction_client_handles_timeout_connection_missing_secret_and_bad_responses():
    def timeout(_request, timeout):
        raise URLError("private host")

    client = PredictionServiceClient(base_url="http://hidden:8103", secret=SECRET, opener=timeout)
    with pytest.raises(PredictionServiceUnavailable, match="unavailable"):
        client.run(RECORDS)

    def connection_error(_request, timeout):
        raise ConnectionError("private host")

    client = PredictionServiceClient(base_url="http://hidden:8103", secret=SECRET, opener=connection_error)
    with pytest.raises(PredictionServiceUnavailable, match="unavailable"):
        client.run(RECORDS)

    missing_secret = PredictionServiceClient(base_url="http://hidden:8103", secret="short")
    with pytest.raises(PredictionServiceUnavailable, match="not configured"):
        missing_secret.run(RECORDS)

    wrong_stage = PredictionServiceClient(
        base_url="http://hidden:8103",
        secret=SECRET,
        opener=lambda *_args, **_kwargs: FakeResponse({"stage": "training"}),
    )
    with pytest.raises(PredictionServiceUnavailable, match="incompatible response"):
        wrong_stage.run(RECORDS)

    class InvalidJSONResponse(FakeResponse):
        def __init__(self):
            self.status = 200
            self.payload = b"not json"

    invalid_json = PredictionServiceClient(
        base_url="http://hidden:8103",
        secret=SECRET,
        opener=lambda *_args, **_kwargs: InvalidJSONResponse(),
    )
    with pytest.raises(PredictionServiceUnavailable, match="invalid response"):
        invalid_json.run(RECORDS)


def test_prediction_client_rejects_non_serializable_records_without_exposing_details():
    client = PredictionServiceClient(base_url="http://hidden:8103", secret=SECRET)
    with pytest.raises(PredictionServiceRejected, match="request data is invalid"):
        client.run([{"month": "2026-09", "value": float("nan")}])


def test_prediction_client_timeout_validation(monkeypatch):
    calls = []
    monkeypatch.setenv("PREDICTION_SERVICE_TIMEOUT_SECONDS", "2.5")
    client = PredictionServiceClient(base_url="http://prediction:8103", secret=SECRET,
                                     opener=lambda _request, timeout: (calls.append(timeout), FakeResponse(_legacy_forecast_response()))[1])
    client.run(RECORDS)
    assert calls == [2.5]

    monkeypatch.delenv("PREDICTION_SERVICE_TIMEOUT_SECONDS")
    default_client = PredictionServiceClient(base_url="http://prediction:8103", secret=SECRET,
                                             opener=lambda _request, timeout: (calls.append(timeout), FakeResponse(_legacy_forecast_response()))[1])
    default_client.run(RECORDS)
    assert calls[-1] == 120

    for invalid in ("", "not-a-number", "0", "-1", "NaN", "Infinity", "-Infinity"):
        monkeypatch.setenv("PREDICTION_SERVICE_TIMEOUT_SECONDS", invalid)
        client = PredictionServiceClient(base_url="http://prediction:8103", secret=SECRET,
                                         opener=lambda *_args, **_kwargs: pytest.fail("opener must not be called"))
        with pytest.raises(PredictionServiceUnavailable, match="timeout configuration is invalid"):
            client.run(RECORDS)

    for invalid in ("", "not-a-number", 0, -1, float("nan"), float("inf")):
        client = PredictionServiceClient(base_url="http://prediction:8103", secret=SECRET,
                                         timeout_seconds=invalid,
                                         opener=lambda *_args, **_kwargs: pytest.fail("opener must not be called"))
        with pytest.raises(PredictionServiceUnavailable, match="timeout configuration is invalid"):
            client.run(RECORDS)


@pytest.mark.parametrize(
    "operation,response,valid",
    [
        ("train_nem", _nem_train_response(), True),
        ("run_nem", _nem_forecast_response(), True),
        ("run_nem", {key: value for key, value in _nem_forecast_response().items() if key != "model_name"}, False),
        ("run_nem", {**_nem_forecast_response(), "model_name": None}, False),
        ("run_nem", {**_nem_forecast_response(), "predicted_demand": "18000"}, False),
        ("run_nem", {**_nem_forecast_response(), "dataset_provenance": {**_nem_forecast_response()["dataset_provenance"], "network_code": "NSW1"}}, False),
        ("run_nem", {key: value for key, value in _nem_forecast_response().items() if key != "predicted_demand"}, False),
        ("train_nem", {**_nem_train_response(), "validation": {}}, False),
        ("train_nem", {**_nem_train_response(), "validation": {**_nem_train_response()["validation"], "overall": {}}}, False),
        ("run_nem", {**_nem_forecast_response(), "predicted_demand": float("nan")}, False),
        ("run_nem", {**_nem_forecast_response(), "predicted_demand": float("inf")}, False),
        ("run_nem", {**_nem_forecast_response(), "stage": "training"}, False),
    ],
)
def test_prediction_client_validates_nem_response_contract(operation, response, valid):
    client = PredictionServiceClient(
        base_url="http://prediction:8103", secret=SECRET,
        opener=lambda *_args, **_kwargs: FakeResponse(response),
    )
    call = {"train_nem": client.train_nem, "run_nem": client.run_nem}[operation]
    request = {"as_of_date": "2026-11-26", "cutoff_date": "2026-11-25", "forecast_date": "2026-11-27",
               "forecast": {"as_of_date": "2026-11-26", "cutoff_date": "2026-11-25", "forecast_date": "2026-11-27"}}
    if valid:
        assert call(request) == response
    else:
        with pytest.raises(PredictionServiceUnavailable, match="incompatible response"):
            call(request)


def test_nem_train_diagnostic_logs_are_correlated_and_sanitized(caplog):
    caplog.set_level(logging.WARNING, logger="app.clients.prediction")
    secret_value = "do-not-log-header-secret-value-at-least-32-bytes"
    private_payload_value = "do-not-log-request-body"
    private_url = "http://private-user:private-pass@private-host:8103/internal?token=url-secret"

    def http_error(request, timeout):
        raise HTTPError(request.full_url, 500, "private response body", None,
                        BytesIO(b"do-not-log-response-body"))

    client = PredictionServiceClient(
        base_url=private_url, secret=secret_value, opener=http_error,
    )
    with prediction_diagnostic_context("gateway-train-http-001"):
        with pytest.raises(PredictionServiceUnavailable):
            client.train_nem({"marker": private_payload_value})

    http_logs = caplog.text
    assert "request_id=gateway-train-http-001" in http_logs
    assert "operation=nem/train" in http_logs
    assert "stage=client_http" in http_logs
    assert "exception_class=HTTPError" in http_logs
    assert "status_code=500" in http_logs
    for sensitive in (secret_value, private_payload_value, "private-user", "private-pass",
                      "private-host", "url-secret", "response body", "do-not-log-response-body"):
        assert sensitive not in http_logs

    class InvalidJSON(FakeResponse):
        def __init__(self):
            self.status = 200
            self.payload = b"do-not-log-json-body"

    invalid_json_client = PredictionServiceClient(
        base_url="http://prediction:8103", secret=secret_value,
        opener=lambda *_args, **_kwargs: InvalidJSON(),
    )
    with prediction_diagnostic_context("gateway-train-json-002"):
        with pytest.raises(PredictionServiceUnavailable, match="invalid response"):
            invalid_json_client.train_nem({})
    assert "request_id=gateway-train-json-002" in caplog.text
    assert "stage=response_json" in caplog.text
    assert "exception_class=JSONDecodeError" in caplog.text
    assert "do-not-log-json-body" not in caplog.text

    invalid_response = _nem_train_response()
    invalid_response["network_code"] = "do-not-log-response-value"
    validation_client = PredictionServiceClient(
        base_url="http://prediction:8103", secret=secret_value,
        opener=lambda *_args, **_kwargs: FakeResponse(invalid_response),
    )
    with prediction_diagnostic_context("gateway-train-validation-003"):
        with pytest.raises(PredictionServiceUnavailable, match="incompatible response"):
            validation_client.train_nem({})
    assert "request_id=gateway-train-validation-003" in caplog.text
    assert "stage=response_validation" in caplog.text
    assert "exception_class=ValueError" in caplog.text
    assert "validation_fields=network_code" in caplog.text
    assert "validation_kind=invalid" in caplog.text
    assert "do-not-log-response-value" not in caplog.text
