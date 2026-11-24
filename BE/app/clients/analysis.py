
import json
import logging
import os
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)


class AnalysisServiceUnavailable(RuntimeError):
    """The internal analysis service could not provide a usable response."""


class AnalysisServiceRejected(RuntimeError):
    """The internal service rejected a validated analysis request."""


class AnalysisServiceClient:
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

    def analyze(self, operation: str, records: list[dict], **options) -> dict:
        if operation not in {
            "summary", "trend", "seasonality", "correlation", "distribution"
        }:
            raise ValueError("Unsupported analysis operation")

        base_url = (
            self._base_url
            or os.getenv("ANALYSIS_SERVICE_URL", "http://127.0.0.1:8101")
        ).rstrip("/")

        secret = (
            self._secret
            if self._secret is not None
            else os.getenv("ANALYSIS_SERVICE_SECRET", "")
        )

        timeout_seconds = (
            self._timeout_seconds
            if self._timeout_seconds is not None
            else float(os.getenv("ANALYSIS_SERVICE_TIMEOUT_SECONDS", "5"))
        )

        if len(secret.encode("utf-8")) < 32:
            logger.error(
                "Analysis Service secret is missing or shorter than 32 bytes"
            )
            raise AnalysisServiceUnavailable("Analysis service is not configured")

        payload = {"records": records, **options}

        try:
            request_body = json.dumps(payload, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError):
            logger.exception(
                "Analysis Service request serialization failed: operation=%s",
                operation,
            )
            raise AnalysisServiceUnavailable(
                "Analysis records cannot be serialized"
            )

        url = f"{base_url}/internal/analysis/{operation}"

        request = Request(
            url,
            data=request_body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Analysis-Service-Secret": secret,
            },
            method="POST",
        )

        logger.info(
            "Calling Analysis Service: operation=%s, url=%s, records=%s",
            operation,
            url,
            len(records),
        )

        try:
            with self._opener(request, timeout=timeout_seconds) as response:
                status_code = response.status
                response_body = response.read()

        except HTTPError as exc:
            logger.error(
                "Analysis Service HTTP error: operation=%s, status=%s",
                operation,
                exc.code,
            )

            if exc.code == 422:
                raise AnalysisServiceRejected(
                    "Analysis service rejected the request"
                ) from exc

            raise AnalysisServiceUnavailable(
                "Analysis service returned an error"
            ) from exc

        except (URLError, TimeoutError, OSError) as exc:
            logger.exception(
                "Cannot connect to Analysis Service: operation=%s, url=%s",
                operation,
                url,
            )
            raise AnalysisServiceUnavailable(
                "Analysis service is unavailable"
            ) from exc

        logger.info(
            "Analysis Service response: operation=%s, status=%s",
            operation,
            status_code,
        )

        if status_code < 200 or status_code >= 300:
            logger.error(
                "Unexpected Analysis Service status: operation=%s, status=%s",
                operation,
                status_code,
            )
            raise AnalysisServiceUnavailable(
                "Analysis service returned an unexpected status"
            )

        try:
            result = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.exception(
                "Analysis Service returned invalid JSON: operation=%s",
                operation,
            )
            raise AnalysisServiceUnavailable(
                "Analysis service returned an invalid response"
            )

        if not isinstance(result, dict):
            logger.error(
                "Analysis Service returned a non-object response: operation=%s",
                operation,
            )
            raise AnalysisServiceUnavailable(
                "Analysis service returned an invalid response"
            )

        return result


analysis_service_client = AnalysisServiceClient()
