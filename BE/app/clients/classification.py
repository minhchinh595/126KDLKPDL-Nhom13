import json
import logging
import math
import os
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)


class ClassificationServiceUnavailable(RuntimeError):
    """The internal Classification Service could not be reached."""


class ClassificationServiceConflict(RuntimeError):
    """The saved Classification artifact is missing or invalid."""


class ClassificationServiceRejected(RuntimeError):
    """The Classification Service rejected supplied records."""


class ClassificationArtifactWriteError(RuntimeError):
    """The Classification Service could not save its model artifact."""


class ClassificationServiceError(RuntimeError):
    """The Classification Service failed while processing the request."""


class ClassificationServiceClient:
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
            or os.getenv("CLASSIFICATION_SERVICE_URL", "http://127.0.0.1:8104")
        ).rstrip("/")
        secret = (
            self._secret
            if self._secret is not None
            else os.getenv("CLASSIFICATION_SERVICE_SECRET", "")
        )
        configured_timeout = self._timeout_seconds
        if configured_timeout is None:
            configured_timeout = os.getenv("CLASSIFICATION_SERVICE_TIMEOUT_SECONDS")
        try:
            if configured_timeout is None or (
                isinstance(configured_timeout, str) and not configured_timeout.strip()
            ):
                raise ValueError
            timeout_seconds = float(configured_timeout)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ClassificationServiceUnavailable(
                "Classification Service timeout is not configured or invalid"
            ) from exc
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ClassificationServiceUnavailable(
                "Classification Service timeout is not configured or invalid"
            )
        if len(secret.encode("utf-8")) < 32:
            raise ClassificationServiceUnavailable("Classification Service is not configured")

        try:
            request_body = json.dumps({"records": records}, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ClassificationServiceRejected("Classification request data is invalid") from exc

        request = Request(
            f"{base_url}/internal/classification/{operation}",
            data=request_body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Classification-Service-Secret": secret,
            },
            method="POST",
        )
        logger.info("Calling Classification Service: operation=%s", operation)

        try:
            with self._opener(request, timeout=timeout_seconds) as response:
                status_code = response.status
                response_body = response.read()
        except HTTPError as exc:
            logger.warning(
                "Classification Service returned an error: operation=%s, status=%s",
                operation,
                exc.code,
            )
            if exc.code == 409:
                raise ClassificationServiceConflict(
                    "Classification artifact is missing or incompatible. An Admin must train the model again."
                ) from exc
            if exc.code == 422:
                raise ClassificationServiceRejected(
                    "Classification Service rejected the request"
                ) from exc
            if exc.code == 507:
                if operation == "train":
                    raise ClassificationArtifactWriteError(
                        "Classification model artifact could not be saved"
                    ) from exc
                raise ClassificationServiceError(
                    "Classification Service could not complete the operation"
                ) from exc
            if exc.code == 500:
                raise ClassificationServiceError(
                    "Classification Service could not complete the operation"
                ) from exc
            raise ClassificationServiceUnavailable(
                "Classification Service returned an error"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            logger.warning("Cannot connect to Classification Service: operation=%s", operation)
            raise ClassificationServiceUnavailable(
                "Classification Service is unavailable"
            ) from exc

        if status_code == 409:
            raise ClassificationServiceConflict(
                "Classification artifact is missing or incompatible. An Admin must train the model again."
            )
        if status_code == 422:
            raise ClassificationServiceRejected("Classification Service rejected the request")
        if status_code == 507:
            if operation == "train":
                raise ClassificationArtifactWriteError(
                    "Classification model artifact could not be saved"
                )
            raise ClassificationServiceError(
                "Classification Service could not complete the operation"
            )
        if status_code == 500:
            raise ClassificationServiceError(
                "Classification Service could not complete the operation"
            )
        if status_code < 200 or status_code >= 300:
            raise ClassificationServiceUnavailable(
                "Classification Service returned an unexpected status"
            )

        try:
            result = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ClassificationServiceUnavailable(
                "Classification Service returned an invalid response"
            ) from exc
        if (
            not isinstance(result, dict)
            or result.get("stage") != expected_stage
            or result.get("model_name") != "RandomForestClassifier"
            or isinstance(result.get("window_months"), bool)
            or not isinstance(result.get("window_months"), int)
            or result.get("window_months") != 12
        ):
            raise ClassificationServiceUnavailable(
                "Classification Service returned an incompatible response"
            )
        return result


classification_service_client = ClassificationServiceClient()
