import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from app.clients.prediction import (
    PredictionArtifactWriteError,
    PredictionServiceClient,
    PredictionServiceConflict,
    PredictionServiceRejected,
    PredictionServiceUnavailable,
)


SECRET = "prediction-test-secret-with-at-least-32-bytes"
RECORDS = [{"month": "2026-08", "value": 28.5}, {"month": "2026-09", "value": 30.3}]


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
    responses = iter([FakeResponse({"stage": "training"}), FakeResponse({"stage": "forecast"})])

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
    assert client.train(RECORDS) == {"stage": "training"}
    assert client.run(RECORDS) == {"stage": "forecast"}
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
