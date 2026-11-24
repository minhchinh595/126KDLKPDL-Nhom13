import json
import logging
import os
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)


class PredictionServiceUnavailable(RuntimeError):
    """The internal Prediction Service could not provide a response."""


class PredictionServiceConflict(RuntimeError):
    """The saved Prediction artifact is missing or incompatible."""


class PredictionServiceRejected(RuntimeError):
    """The Prediction Service rejected supplied records."""


class PredictionArtifactWriteError(RuntimeError):
    """The Prediction Service could not save its model artifact."""


class PredictionServiceClient:
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

    def train(self, records: list[dict]) -> dict:
        return self._post("train", records, expected_stage="training")

    def run(self, records: list[dict]) -> dict:
        return self._post("run", records, expected_stage="forecast")

    def _post(self, operation: str, records: list[dict], *, expected_stage: str) -> dict:
        base_url = (
            self._base_url
            or os.getenv("PREDICTION_SERVICE_URL", "http://127.0.0.1:8103")
        ).rstrip("/")
        secret = self._secret if self._secret is not None else os.getenv("PREDICTION_SERVICE_SECRET", "")
        timeout_seconds = (
            self._timeout_seconds
            if self._timeout_seconds is not None
            else float(os.getenv("PREDICTION_SERVICE_TIMEOUT_SECONDS", "120"))
        )
        if len(secret.encode("utf-8")) < 32:
            raise PredictionServiceUnavailable("Prediction Service is not configured")

        try:
            request_body = json.dumps({"records": records}, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise PredictionServiceRejected("Prediction request data is invalid") from exc

        request = Request(
            f"{base_url}/internal/prediction/{operation}",
            data=request_body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Prediction-Service-Secret": secret,
            },
            method="POST",
        )
        logger.info("Calling Prediction Service: operation=%s", operation)

        try:
            with self._opener(request, timeout=timeout_seconds) as response:
                status_code = response.status
                response_body = response.read()
        except HTTPError as exc:
            logger.warning(
                "Prediction Service returned an error: operation=%s, status=%s",
                operation,
                exc.code,
            )
            if exc.code == 409:
                raise PredictionServiceConflict(
                    "Prediction artifact is missing or incompatible. An Admin must train the model again."
                ) from exc
            if exc.code == 422:
                raise PredictionServiceRejected("Prediction Service rejected the request") from exc
            if exc.code == 507:
                raise PredictionArtifactWriteError(
                    "Prediction model artifact could not be saved"
                ) from exc
            raise PredictionServiceUnavailable("Prediction Service returned an error") from exc
        except (URLError, TimeoutError, OSError) as exc:
            logger.warning("Cannot connect to Prediction Service: operation=%s", operation)
            raise PredictionServiceUnavailable("Prediction Service is unavailable") from exc

        if status_code == 409:
            raise PredictionServiceConflict(
                "Prediction artifact is missing or incompatible. An Admin must train the model again."
            )
        if status_code == 422:
            raise PredictionServiceRejected("Prediction Service rejected the request")
        if status_code == 507:
            raise PredictionArtifactWriteError("Prediction model artifact could not be saved")
        if status_code < 200 or status_code >= 300:
            raise PredictionServiceUnavailable("Prediction Service returned an unexpected status")

        try:
            result = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PredictionServiceUnavailable("Prediction Service returned an invalid response") from exc
        if not isinstance(result, dict) or result.get("stage") != expected_stage:
            raise PredictionServiceUnavailable("Prediction Service returned an incompatible response")
        return result


prediction_service_client = PredictionServiceClient()
