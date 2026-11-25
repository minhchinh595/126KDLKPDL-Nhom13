"""HTTP client for the Open Electricity API (NEM)."""

import json
import math
import os
import socket
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from app.nem.schemas import (
    NEMAPIRejected,
    NEMObservationRecord,
    NEMResponseValidationError,
    parse_response,
    validate_request_spec,
)


DEFAULT_API_BASE_URL = "https://api.openelectricity.org.au/v4"
DEFAULT_TIMEOUT_SECONDS = 30.0
NEM_TIMEZONE = ZoneInfo("Australia/Brisbane")
USER_AGENT = "DoAn-KhoDuLieu-NEM-Ingestion/0.1 (Python)"


class NEMClientError(RuntimeError):
    """Base error for Open Electricity client failures."""


class NEMConfigurationError(NEMClientError):
    """The client is missing valid API configuration."""


class NEMHTTPError(NEMClientError):
    """The API returned a non-success HTTP status."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"Open Electricity API returned HTTP {status_code}")


class NEMTimeoutError(NEMClientError):
    """The Open Electricity request timed out."""


class NEMConnectionError(NEMClientError):
    """The client could not connect to Open Electricity."""


class NEMAPIError(NEMClientError):
    """The API rejected the request or returned an invalid response."""


class OpenElectricityClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | str | None = None,
        opener: Callable | None = None,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._opener = opener or urlopen

    def get_observations(
        self,
        network_code: str,
        metrics: Sequence[str],
        interval: str,
        date_start: datetime,
        date_end: datetime,
        primary_grouping: str = "network",
    ) -> list[NEMObservationRecord]:
        metric_names = validate_request_spec(
            network_code, metrics, interval, primary_grouping
        )
        self._validate_dates(date_start, date_end)
        base_url = self._configured_base_url()
        api_key = self._configured_api_key()
        timeout_seconds = self._configured_timeout()

        query = [("metrics", metric) for metric in metric_names]
        query.extend(
            [
                ("interval", interval),
                ("date_start", self._network_time_query_value(date_start)),
                ("date_end", self._network_time_query_value(date_end)),
                ("primary_grouping", primary_grouping),
            ]
        )
        url = (
            f"{base_url}/market/network/{quote(network_code, safe='')}?"
            f"{urlencode(query)}"
        )
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": USER_AGENT,
            },
            method="GET",
        )

        try:
            with self._opener(request, timeout=timeout_seconds) as response:
                status = getattr(response, "status", None)
                if status is None and hasattr(response, "getcode"):
                    status = response.getcode()
                if status is not None and not 200 <= status < 300:
                    raise NEMHTTPError(int(status))
                body = response.read()
        except NEMHTTPError:
            raise
        except HTTPError as exc:
            raise NEMHTTPError(exc.code) from None
        except (socket.timeout, TimeoutError) as exc:
            raise NEMTimeoutError("Open Electricity API request timed out") from None
        except URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise NEMTimeoutError("Open Electricity API request timed out") from None
            raise NEMConnectionError("Could not connect to Open Electricity API") from None
        except OSError as exc:
            raise NEMConnectionError("Could not connect to Open Electricity API") from None

        try:
            payload = json.loads(body, parse_float=Decimal)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise NEMAPIError("Open Electricity API returned invalid JSON") from None

        try:
            return parse_response(
                payload,
                expected_network_code=network_code,
                expected_metrics=metric_names,
                expected_interval=interval,
                primary_grouping=primary_grouping,
            )
        except NEMAPIRejected as exc:
            raise NEMAPIError("Open Electricity API reported success=false") from None
        except NEMResponseValidationError as exc:
            raise NEMAPIError("Open Electricity API returned an invalid response") from None

    def _configured_base_url(self) -> str:
        if self._base_url is not None:
            value = self._base_url
        else:
            value = os.getenv("OPEN_ELECTRICITY_BASE_URL")
            if value is None or not value.strip():
                value = os.getenv("OPEN_ELECTRICITY_API_BASE_URL")
            if value is None:
                value = DEFAULT_API_BASE_URL
        if not isinstance(value, str) or not value.strip():
            raise NEMConfigurationError("OPEN_ELECTRICITY_BASE_URL is not configured")
        value = value.strip().rstrip("/")
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise NEMConfigurationError("OPEN_ELECTRICITY_BASE_URL is invalid")
        return value

    @staticmethod
    def _network_time_query_value(value: datetime) -> str:
        """Format an aware instant as timezone-naive NEM network wall time."""
        return value.astimezone(NEM_TIMEZONE).replace(tzinfo=None).isoformat()

    def _configured_api_key(self) -> str:
        value = self._api_key if self._api_key is not None else os.getenv("OPEN_ELECTRICITY_API_KEY")
        if not isinstance(value, str) or not value.strip():
            raise NEMConfigurationError("OPEN_ELECTRICITY_API_KEY is not configured")
        return value.strip()

    def _configured_timeout(self) -> float:
        raw = (
            self._timeout_seconds
            if self._timeout_seconds is not None
            else os.getenv("OPEN_ELECTRICITY_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
        )
        if isinstance(raw, bool):
            raise NEMConfigurationError("OPEN_ELECTRICITY_TIMEOUT_SECONDS must be a positive finite number")
        try:
            timeout = float(raw)
        except (TypeError, ValueError, OverflowError):
            raise NEMConfigurationError(
                "OPEN_ELECTRICITY_TIMEOUT_SECONDS must be a positive finite number"
            ) from None
        if not math.isfinite(timeout) or timeout <= 0:
            raise NEMConfigurationError(
                "OPEN_ELECTRICITY_TIMEOUT_SECONDS must be a positive finite number"
            )
        return timeout

    @staticmethod
    def _validate_dates(date_start: datetime, date_end: datetime) -> None:
        if not isinstance(date_start, datetime) or not isinstance(date_end, datetime):
            raise NEMResponseValidationError("date_start and date_end must be datetime values")
        if (
            date_start.tzinfo is None
            or date_start.utcoffset() is None
            or date_end.tzinfo is None
            or date_end.utcoffset() is None
        ):
            raise NEMResponseValidationError("date_start and date_end must be timezone-aware")
        if date_start.astimezone(timezone.utc) >= date_end.astimezone(timezone.utc):
            raise NEMResponseValidationError("date_start must be earlier than date_end")


open_electricity_client = OpenElectricityClient()
