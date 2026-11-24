import json
import logging
import math
import os
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)
RECORD_FIELDS = {
    "country_id", "country", "iso3", "month", "metric", "fuel", "value", "unit"
}


class IngestionServiceUnavailable(RuntimeError):
    """The internal Ingestion Service is unavailable or returned an invalid response."""


class IngestionServiceRejected(RuntimeError):
    """The Ingestion Service rejected the uploaded CSV as invalid."""


class IngestionFileTooLarge(RuntimeError):
    """The CSV exceeded the configured upload size limit."""


@dataclass(frozen=True)
class NormalizedCSV:
    rows: list[dict]
    rows_read: int
    start_month: date
    end_month: date


class IngestionServiceClient:
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

    def normalize(self, content: bytes) -> NormalizedCSV:
        base_url = (
            self._base_url
            or os.getenv("INGESTION_SERVICE_URL", "http://127.0.0.1:8105")
        ).rstrip("/")
        secret = (
            self._secret
            if self._secret is not None
            else os.getenv("INGESTION_SERVICE_SECRET", "")
        )
        raw_timeout = self._timeout_seconds
        if raw_timeout is None:
            raw_timeout = os.getenv("INGESTION_SERVICE_TIMEOUT_SECONDS", "30")
        try:
            if isinstance(raw_timeout, str) and not raw_timeout.strip():
                raise ValueError
            timeout = float(raw_timeout)
        except (TypeError, ValueError, OverflowError) as exc:
            raise IngestionServiceUnavailable(
                "Ingestion Service timeout configuration is invalid"
            ) from exc
        if not math.isfinite(timeout) or timeout <= 0:
            raise IngestionServiceUnavailable(
                "Ingestion Service timeout configuration is invalid"
            )
        if len(secret.encode("utf-8")) < 32:
            raise IngestionServiceUnavailable("Ingestion Service is not configured")
        if not isinstance(content, bytes):
            raise IngestionServiceRejected("CSV request content is invalid")

        boundary = f"----electricity-ingestion-{uuid.uuid4().hex}"
        body = b"\r\n".join((
            f"--{boundary}".encode(),
            b'Content-Disposition: form-data; name="file"; filename="upload.csv"',
            b"Content-Type: text/csv; charset=utf-8",
            b"",
            content,
            f"--{boundary}--".encode(),
            b"",
        ))
        try:
            request = Request(
                f"{base_url}/internal/ingestion/normalize",
                data=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "X-Ingestion-Service-Secret": secret,
                },
                method="POST",
            )
        except (TypeError, ValueError) as exc:
            raise IngestionServiceUnavailable("Ingestion Service URL is invalid") from exc

        logger.info("Calling Ingestion Service: operation=normalize, bytes=%s", len(content))
        try:
            with self._opener(request, timeout=timeout) as response:
                status_code = response.status
                response_body = response.read()
        except HTTPError as exc:
            logger.warning("Ingestion Service returned an error: status=%s", exc.code)
            self._raise_for_status(exc.code, exc.read())
            raise AssertionError("unreachable")
        except ValueError as exc:
            logger.warning("Ingestion Service request could not be opened")
            raise IngestionServiceUnavailable("Ingestion Service is unavailable") from exc
        except (URLError, TimeoutError, OSError) as exc:
            logger.warning("Cannot connect to Ingestion Service")
            raise IngestionServiceUnavailable("Ingestion Service is unavailable") from exc

        if status_code < 200 or status_code >= 300:
            self._raise_for_status(status_code, response_body)
        try:
            payload = json.loads(response_body)
            return self._validate_response(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, InvalidOperation) as exc:
            raise IngestionServiceUnavailable(
                "Ingestion Service returned an invalid response"
            ) from exc

    @staticmethod
    def _raise_for_status(status_code: int, response_body: bytes) -> None:
        if status_code == 413:
            raise IngestionFileTooLarge("CSV exceeds the upload size limit")
        if status_code == 422:
            detail = "CSV validation failed"
            try:
                error_payload = json.loads(response_body)
                if isinstance(error_payload, dict) and isinstance(error_payload.get("detail"), str):
                    detail = error_payload["detail"][:2000]
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
                pass
            raise IngestionServiceRejected(detail)
        raise IngestionServiceUnavailable("Ingestion Service returned an error")

    @staticmethod
    def _validate_response(payload: object) -> NormalizedCSV:
        if not isinstance(payload, dict) or set(payload) != {
            "rows", "rows_read", "start_month", "end_month"
        }:
            raise ValueError("response fields do not match the contract")
        rows = payload["rows"]
        rows_read = payload["rows_read"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("rows must be a non-empty array")
        if isinstance(rows_read, bool) or not isinstance(rows_read, int) or rows_read != len(rows):
            raise ValueError("rows_read does not match rows")

        normalized_rows = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != RECORD_FIELDS:
                raise ValueError("row fields do not match the contract")
            if (
                not isinstance(row["country_id"], str) or not row["country_id"]
                or not isinstance(row["country"], str) or not row["country"]
                or row["iso3"] != "VNM"
                or row["metric"] != "demand"
                or row["fuel"] is not None
                or row["unit"] != "TWh"
                or not isinstance(row["month"], str)
                or not isinstance(row["value"], str)
            ):
                raise ValueError("row values do not match the contract")
            month = date.fromisoformat(row["month"])
            value = Decimal(row["value"])
            if month.day != 1 or not value.is_finite() or value < 0:
                raise ValueError("row month or value is invalid")
            if len(value.as_tuple().digits) > 14 or max(-value.as_tuple().exponent, 0) > 4:
                raise ValueError("row value exceeds supported precision")
            normalized_rows.append({**row, "month": month, "value": value})

        start_month = IngestionServiceClient._parse_month_field(payload["start_month"])
        end_month = IngestionServiceClient._parse_month_field(payload["end_month"])
        months = [row["month"] for row in normalized_rows]
        if start_month != min(months) or end_month != max(months):
            raise ValueError("month range does not match rows")
        return NormalizedCSV(normalized_rows, rows_read, start_month, end_month)

    @staticmethod
    def _parse_month_field(value: object) -> date:
        if not isinstance(value, str):
            raise ValueError("month metadata must be a string")
        month = date.fromisoformat(value)
        if month.day != 1:
            raise ValueError("month metadata must use the first day of a month")
        return month


ingestion_service_client = IngestionServiceClient()
