import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from app.clients.classification import (
    ClassificationArtifactWriteError,
    ClassificationServiceClient,
    ClassificationServiceConflict,
    ClassificationServiceError,
    ClassificationServiceRejected,
    ClassificationServiceUnavailable,
)


SECRET = "classification-test-secret-with-at-least-32-bytes"
RECORDS = [{"month": "2026-08", "value": 28.5}, {"month": "2026-09", "value": 30.3}]
TRAIN_RESULT = {"stage": "training", "model_name": "RandomForestClassifier", "window_months": 12}
RUN_RESULT = {"stage": "forecast", "model_name": "RandomForestClassifier", "window_months": 12}


@pytest.fixture(autouse=True)
def configured_timeout(monkeypatch):
    monkeypatch.setenv("CLASSIFICATION_SERVICE_TIMEOUT_SECONDS", "120")


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


def test_classification_client_posts_train_and_run_with_secret_timeout_and_payload():
    captured = []
    responses = iter([FakeResponse(TRAIN_RESULT), FakeResponse(RUN_RESULT)])

    def opener(request, timeout):
        captured.append({
            "url": request.full_url,
            "secret": request.get_header("X-classification-service-secret"),
            "payload": json.loads(request.data),
            "timeout": timeout,
        })
        return next(responses)

    client = ClassificationServiceClient(
        base_url="http://classification.internal:8104/",
        secret=SECRET,
        timeout_seconds=120,
        opener=opener,
    )
    assert client.train(RECORDS) == TRAIN_RESULT
    assert client.run(RECORDS) == RUN_RESULT
    assert captured == [
        {
            "url": "http://classification.internal:8104/internal/classification/train",
            "secret": SECRET,
            "payload": {"records": RECORDS},
            "timeout": 120,
        },
        {
            "url": "http://classification.internal:8104/internal/classification/run",
            "secret": SECRET,
            "payload": {"records": RECORDS},
            "timeout": 120,
        },
    ]


@pytest.mark.parametrize(
    "status,error_type",
    [
        (409, ClassificationServiceConflict),
        (422, ClassificationServiceRejected),
        (500, ClassificationServiceError),
        (503, ClassificationServiceUnavailable),
        (507, ClassificationServiceError),
    ],
)
def test_classification_client_maps_http_errors_without_leaking_details(status, error_type):
    def opener(request, timeout):
        raise HTTPError(request.full_url, status, "failed", None, BytesIO(b"private artifact path and secret"))

    client = ClassificationServiceClient(
        base_url="http://hidden:8104",
        secret=SECRET,
        opener=opener,
    )
    with pytest.raises(error_type) as error:
        client.run(RECORDS)
    assert "private artifact path" not in str(error.value)
    assert "hidden" not in str(error.value)
    assert SECRET not in str(error.value)


def test_classification_client_handles_timeout_connection_and_missing_secret():
    def timeout(_request, timeout):
        raise URLError("private host")

    client = ClassificationServiceClient(
        base_url="http://hidden:8104",
        secret=SECRET,
        opener=timeout,
    )
    with pytest.raises(ClassificationServiceUnavailable, match="unavailable"):
        client.run(RECORDS)

    def connection_error(_request, timeout):
        raise ConnectionError("private host")

    disconnected = ClassificationServiceClient(
        base_url="http://hidden:8104",
        secret=SECRET,
        opener=connection_error,
    )
    with pytest.raises(ClassificationServiceUnavailable, match="unavailable"):
        disconnected.run(RECORDS)

    missing_secret = ClassificationServiceClient(base_url="http://hidden:8104", secret="short")
    with pytest.raises(ClassificationServiceUnavailable, match="not configured"):
        missing_secret.run(RECORDS)


def test_classification_client_rejects_invalid_json_non_object_and_wrong_stage():
    class InvalidJSONResponse(FakeResponse):
        def __init__(self):
            self.status = 200
            self.payload = b"not json"

    invalid_json = ClassificationServiceClient(
        base_url="http://hidden:8104",
        secret=SECRET,
        opener=lambda *_args, **_kwargs: InvalidJSONResponse(),
    )
    with pytest.raises(ClassificationServiceUnavailable, match="invalid response"):
        invalid_json.run(RECORDS)

    non_object = ClassificationServiceClient(
        base_url="http://hidden:8104",
        secret=SECRET,
        opener=lambda *_args, **_kwargs: FakeResponse(["not", "an", "object"]),
    )
    with pytest.raises(ClassificationServiceUnavailable, match="incompatible response"):
        non_object.run(RECORDS)

    wrong_stage = ClassificationServiceClient(
        base_url="http://hidden:8104",
        secret=SECRET,
        opener=lambda *_args, **_kwargs: FakeResponse({**RUN_RESULT, "stage": "training"}),
    )
    with pytest.raises(ClassificationServiceUnavailable, match="incompatible response"):
        wrong_stage.run(RECORDS)


@pytest.mark.parametrize(
    "timeout_value",
    ["", "   ", "not-a-number", "NaN", "Infinity", "-Infinity", "0", "-0.5"],
)
def test_classification_client_rejects_invalid_timeout_configuration(monkeypatch, timeout_value):
    monkeypatch.setenv("CLASSIFICATION_SERVICE_TIMEOUT_SECONDS", timeout_value)
    called = []
    client = ClassificationServiceClient(secret=SECRET, opener=lambda *_a, **_k: called.append(True))
    with pytest.raises(ClassificationServiceUnavailable, match="timeout"):
        client.run(RECORDS)
    assert called == []


def test_classification_client_rejects_missing_timeout_configuration(monkeypatch):
    monkeypatch.delenv("CLASSIFICATION_SERVICE_TIMEOUT_SECONDS", raising=False)
    called = []
    client = ClassificationServiceClient(secret=SECRET, opener=lambda *_a, **_k: called.append(True))
    with pytest.raises(ClassificationServiceUnavailable, match="timeout"):
        client.run(RECORDS)
    assert called == []


def test_classification_client_accepts_valid_timeout_configuration(monkeypatch):
    monkeypatch.setenv("CLASSIFICATION_SERVICE_TIMEOUT_SECONDS", "0.25")
    captured = []
    client = ClassificationServiceClient(
        secret=SECRET,
        opener=lambda _request, timeout: (captured.append(timeout) or FakeResponse(RUN_RESULT)),
    )
    assert client.run(RECORDS) == RUN_RESULT
    assert captured == [0.25]


@pytest.mark.parametrize(
    "payload",
    [
        {"stage": "forecast", "window_months": 12},
        {"stage": "forecast", "model_name": "RandomForestClassifier"},
        {"stage": "forecast", "model_name": 42, "window_months": 12},
        {"stage": "forecast", "model_name": "RandomForestClassifier", "window_months": "12"},
        {"stage": "forecast", "model_name": "RandomForestClassifier", "window_months": True},
        {"stage": "forecast", "model_name": "RandomForestClassifier", "window_months": 0},
        {"stage": "forecast", "model_name": "RandomForestClassifier", "window_months": 13},
        {"stage": "training", "model_name": "RandomForestClassifier", "window_months": 12},
    ],
)
def test_classification_client_rejects_invalid_response_contract(payload):
    client = ClassificationServiceClient(
        secret=SECRET,
        opener=lambda *_args, **_kwargs: FakeResponse(payload),
    )
    with pytest.raises(ClassificationServiceUnavailable, match="incompatible response"):
        client.run(RECORDS)


def test_classification_client_maps_http_507_train_to_artifact_write_error():
    def opener(request, timeout):
        raise HTTPError(request.full_url, 507, "failed", None, BytesIO(b"private"))

    client = ClassificationServiceClient(secret=SECRET, opener=opener)
    with pytest.raises(ClassificationArtifactWriteError):
        client.train(RECORDS)


def test_classification_client_maps_http_507_run_to_service_error():
    def opener(request, timeout):
        raise HTTPError(request.full_url, 507, "failed", None, BytesIO(b"private"))

    client = ClassificationServiceClient(secret=SECRET, opener=opener)
    with pytest.raises(ClassificationServiceError):
        client.run(RECORDS)


def test_classification_client_maps_response_status_507_by_operation():
    train_client = ClassificationServiceClient(
        secret=SECRET, opener=lambda *_a, **_k: FakeResponse({}, status=507)
    )
    run_client = ClassificationServiceClient(
        secret=SECRET, opener=lambda *_a, **_k: FakeResponse({}, status=507)
    )
    with pytest.raises(ClassificationArtifactWriteError):
        train_client.train(RECORDS)
    with pytest.raises(ClassificationServiceError):
        run_client.run(RECORDS)
