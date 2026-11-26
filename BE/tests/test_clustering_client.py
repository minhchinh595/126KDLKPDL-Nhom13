import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from app.clients.clustering import (
    ClusteringServiceClient,
    ClusteringServiceConflict,
    ClusteringServiceRejected,
    ClusteringServiceUnavailable,
)


SECRET = "clustering-test-secret-with-at-least-32-bytes"
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


def test_clustering_client_posts_train_and_run_with_secret_timeout_and_payload():
    captured = []
    responses = iter([FakeResponse({"stage": "training"}), FakeResponse({"stage": "run"})])

    def opener(request, timeout):
        captured.append({
            "url": request.full_url,
            "secret": request.get_header("X-clustering-service-secret"),
            "payload": json.loads(request.data),
            "timeout": timeout,
        })
        return next(responses)

    client = ClusteringServiceClient(
        base_url="http://clustering.internal:8102/",
        secret=SECRET,
        timeout_seconds=30,
        opener=opener,
    )
    assert client.train(RECORDS, max_k=4) == {"stage": "training"}
    assert client.run(RECORDS) == {"stage": "run"}
    assert captured == [
        {
            "url": "http://clustering.internal:8102/internal/clustering/train",
            "secret": SECRET,
            "payload": {"records": RECORDS, "max_k": 4},
            "timeout": 30,
        },
        {
            "url": "http://clustering.internal:8102/internal/clustering/run",
            "secret": SECRET,
            "payload": {"records": RECORDS},
            "timeout": 30,
        },
    ]


def test_clustering_client_posts_nem_daily_contract_to_internal_endpoints():
    captured = []

    def opener(request, timeout):
        captured.append({
            "url": request.full_url,
            "secret": request.get_header("X-clustering-service-secret"),
            "payload": json.loads(request.data),
            "timeout": timeout,
        })
        stage = "training" if request.full_url.endswith("/nem/train") else "run"
        return FakeResponse({"stage": stage})

    client = ClusteringServiceClient(
        base_url="http://clustering.internal:8102",
        secret=SECRET,
        timeout_seconds=12,
        opener=opener,
    )
    payload = {
        "network_code": "NEM",
        "interval": "1d",
        "configurations": {
            "A": {"records": []},
            "B": {"records": []},
        },
    }

    assert client.train_nem(payload, max_k=4) == {"stage": "training"}
    assert client.run_nem(payload) == {"stage": "run"}

    assert captured == [
        {
            "url": "http://clustering.internal:8102/internal/clustering/nem/train",
            "secret": SECRET,
            "payload": {**payload, "max_k": 4},
            "timeout": 12,
        },
        {
            "url": "http://clustering.internal:8102/internal/clustering/nem/run",
            "secret": SECRET,
            "payload": payload,
            "timeout": 12,
        },
    ]


@pytest.mark.parametrize(
    "status,error_type",
    [
        (409, ClusteringServiceConflict),
        (422, ClusteringServiceRejected),
        (503, ClusteringServiceUnavailable),
    ],
)
def test_clustering_client_maps_internal_http_errors_without_leaking_body(status, error_type):
    def opener(request, timeout):
        raise HTTPError(request.full_url, status, "failed", None, BytesIO(b"private path and secret"))

    client = ClusteringServiceClient(base_url="http://hidden:8102", secret=SECRET, opener=opener)

    with pytest.raises(error_type) as error:
        client.run(RECORDS)

    assert "private path" not in str(error.value)
    assert SECRET not in str(error.value)


def test_clustering_client_handles_timeout_missing_secret_and_bad_response():
    def timeout(_request, timeout):
        raise URLError("private host")

    client = ClusteringServiceClient(base_url="http://hidden:8102", secret=SECRET, opener=timeout)

    with pytest.raises(ClusteringServiceUnavailable, match="unavailable"):
        client.run(RECORDS)

    missing_secret = ClusteringServiceClient(base_url="http://hidden:8102", secret="short")

    with pytest.raises(ClusteringServiceUnavailable, match="not configured"):
        missing_secret.run(RECORDS)

    bad_response = ClusteringServiceClient(
        base_url="http://hidden:8102",
        secret=SECRET,
        opener=lambda *_args, **_kwargs: FakeResponse({"stage": "training"}),
    )

    with pytest.raises(ClusteringServiceUnavailable, match="incompatible response"):
        bad_response.run(RECORDS)
