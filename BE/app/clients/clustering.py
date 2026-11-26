import json
import logging
import os
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)


class ClusteringServiceUnavailable(RuntimeError):
    """The internal Clustering Service could not provide a valid response."""


class ClusteringServiceConflict(RuntimeError):
    """The saved artifact is missing or incompatible with the current data."""


class ClusteringServiceRejected(RuntimeError):
    """The internal service rejected the supplied records or parameters."""


class ClusteringServiceClient:
    def __init__(
        self,
        base_url: str | None = None,
        secret: str | None = None,
        timeout_seconds: float | None = None,
        opener: Callable = urlopen,
    ) -> None:
        self._base_url = base_url
        self._secret = secret
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def train(self, records: list[dict], max_k: int = 5) -> dict:
        return self._post("train", {"records": records, "max_k": max_k}, expected_stage="training")

    def run(self, records: list[dict]) -> dict:
        return self._post("run", {"records": records}, expected_stage="run")

    def train_nem(self, payload: dict, max_k: int = 5) -> dict:
        request_payload = {**payload, "max_k": max_k}
        return self._post("nem/train", request_payload, expected_stage="training")

    def run_nem(self, payload: dict) -> dict:
        return self._post("nem/run", payload, expected_stage="run")

    def _post(self, operation: str, payload: dict, *, expected_stage: str) -> dict:
        base_url = (
            self._base_url
            or os.getenv("CLUSTERING_SERVICE_URL", "http://127.0.0.1:8102")
        ).rstrip("/")
        secret = (
            self._secret
            if self._secret is not None
            else os.getenv("CLUSTERING_SERVICE_SECRET", "")
        )
        timeout_seconds = (
            self._timeout_seconds
            if self._timeout_seconds is not None
            else float(os.getenv("CLUSTERING_SERVICE_TIMEOUT_SECONDS", "30"))
        )
        if len(secret.encode("utf-8")) < 32:
            raise ClusteringServiceUnavailable("Clustering Service is not configured")

        try:
            request_body = json.dumps(payload, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ClusteringServiceRejected("Clustering request data is invalid") from exc

        request = Request(
            f"{base_url}/internal/clustering/{operation}",
            data=request_body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Clustering-Service-Secret": secret,
            },
            method="POST",
        )

        logger.info("Calling Clustering Service: operation=%s", operation)
        try:
            with self._opener(request, timeout=timeout_seconds) as response:
                status_code = response.status
                response_body = response.read()
        except HTTPError as exc:
            logger.warning(
                "Clustering Service rejected operation: operation=%s, status=%s",
                operation,
                exc.code,
            )
            if exc.code == 409:
                raise ClusteringServiceConflict(
                    "Clustering artifact is missing or incompatible. An Admin must train the model again."
                ) from exc
            if exc.code == 422:
                raise ClusteringServiceRejected(
                    "Clustering Service rejected the request"
                ) from exc
            raise ClusteringServiceUnavailable(
                "Clustering Service returned an error"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            logger.exception("Cannot connect to Clustering Service: operation=%s", operation)
            raise ClusteringServiceUnavailable(
                "Clustering Service is unavailable"
            ) from exc

        if status_code == 409:
            raise ClusteringServiceConflict(
                "Clustering artifact is missing or incompatible. An Admin must train the model again."
            )
        if status_code == 422:
            raise ClusteringServiceRejected("Clustering Service rejected the request")
        if status_code < 200 or status_code >= 300:
            raise ClusteringServiceUnavailable("Clustering Service returned an unexpected status")

        try:
            result = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ClusteringServiceUnavailable("Clustering Service returned an invalid response") from exc
        if not isinstance(result, dict) or result.get("stage") != expected_stage:
            raise ClusteringServiceUnavailable("Clustering Service returned an incompatible response")
        return result


clustering_service_client = ClusteringServiceClient()
