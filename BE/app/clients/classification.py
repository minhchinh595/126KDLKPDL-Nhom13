import json
import logging
import math
import os
from datetime import date, datetime, timedelta
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE
from app.services.nem_ml_contract import NEM_H2_ARTIFACT_NAMES


CLASS_PROBABILITY_SUM_TOLERANCE = 2e-6

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

    def train_nem(self, payload: dict) -> dict:
        return self._post_payload("nem/train", payload, expected_stage="training")

    def run_nem(self, payload: dict) -> dict:
        result = self._post_payload("nem/run", payload, expected_stage="forecast")
        forecast = payload.get("forecast")
        if not isinstance(forecast, dict) or any(
            result.get(field) != forecast.get(field)
            for field in ("as_of_date", "cutoff_date", "forecast_date")
        ):
            raise ClassificationServiceUnavailable("Classification Service returned dates inconsistent with the request")
        return result

    def _post(self, operation: str, records: list[dict], *, expected_stage: str) -> dict:
        return self._post_payload(operation, {"records": records}, expected_stage=expected_stage)

    def _post_payload(self, operation: str, payload: dict, *, expected_stage: str) -> dict:
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
            request_body = json.dumps(payload, allow_nan=False).encode("utf-8")
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
        ):
            raise ClassificationServiceUnavailable(
                "Classification Service returned an incompatible response"
            )
        if operation.startswith("nem/"):
            try:
                self._validate_nem_response(result, expected_stage)
            except (TypeError, ValueError, KeyError, OverflowError) as exc:
                raise ClassificationServiceUnavailable(
                    "Classification Service returned an incompatible response"
                ) from exc
        elif (
            isinstance(result.get("window_months"), bool)
            or not isinstance(result.get("window_months"), int)
            or result.get("window_months") != 12
        ):
            raise ClassificationServiceUnavailable(
                "Classification Service returned an incompatible response"
            )
        return result

    @staticmethod
    def _validate_nem_response(result: dict, stage: str) -> None:
        if stage == "training":
            for key, expected in (("target", "daily_demand_level"), ("network_code", "NEM"), ("interval", "1d"), ("unit", "MW"), ("forecast_horizon_days", 2), ("feature_schema_version", "nem_daily_demand_h2_v1")):
                if result.get(key) != expected:
                    raise ValueError(f"{key} is incompatible")
            dataset_id = result.get("dataset_id")
            if isinstance(dataset_id, bool) or not isinstance(dataset_id, int) or dataset_id <= 0:
                raise ValueError("dataset_id is invalid")
            if result.get("dataset_name") != NEM_DATASET_NAME or result.get("dataset_source") != NEM_DATASET_SOURCE:
                raise ValueError("dataset provenance is incompatible")
            for key in ("artifact_name", "training_data_fingerprint"):
                if not isinstance(result.get(key), str) or not result[key].strip():
                    raise ValueError(f"{key} is required")
            if result["artifact_name"] != NEM_H2_ARTIFACT_NAMES["classification"]:
                raise ValueError("artifact_name is not the NEM H2 Classification artifact")
            validation = result.get("validation")
            if not isinstance(validation, dict) or validation.get("strategy") != "TimeSeriesSplit chronological rolling-origin":
                raise ValueError("chronological validation is required")
            if not isinstance(validation.get("folds"), list) or not validation["folds"]:
                raise ValueError("validation folds are required")
            return

        for key, expected in (("target", "daily_demand_level"), ("network_code", "NEM"), ("metric", "demand"), ("interval", "1d"), ("unit", "MW"), ("forecast_status", "ready"), ("horizon_days", 2)):
            if result.get(key) != expected:
                raise ValueError(f"{key} is incompatible")
        forecast = date.fromisoformat(result["forecast_date"])
        cutoff = date.fromisoformat(result["cutoff_date"])
        as_of = date.fromisoformat(result["as_of_date"])
        if forecast != cutoff + timedelta(days=2) or cutoff != as_of - timedelta(days=1) or forecast != as_of + timedelta(days=1):
            raise ValueError("forecast date does not match cutoff")
        if date.fromisoformat(result["last_observed_date"]) != cutoff:
            raise ValueError("last observation does not match cutoff")
        observed_at = datetime.fromisoformat(result["last_observed_at"].replace("Z", "+00:00"))
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("last_observed_at must be timezone-aware")
        if result.get("predicted_level") not in {"Low", "High"}:
            raise ValueError("predicted_level is invalid")
        probabilities = result.get("probabilities")
        if not isinstance(probabilities, dict) or set(probabilities) != {"Low", "High"}:
            raise ValueError("class probabilities are required")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or value > 1 for value in probabilities.values()):
            raise ValueError("class probabilities must be finite values between 0 and 1")
        if not math.isclose(
            probabilities["Low"] + probabilities["High"],
            1.0,
            rel_tol=0.0,
            abs_tol=CLASS_PROBABILITY_SUM_TOLERANCE,
        ):
            raise ValueError(
                "class probabilities must sum to 1 within "
                f"{CLASS_PROBABILITY_SUM_TOLERANCE:g}"
            )
        threshold = result.get("threshold_mw")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or threshold < 0:
            raise ValueError("threshold_mw is invalid")
        provenance = result.get("dataset_provenance")
        if not isinstance(provenance, dict) or provenance.get("dataset_name") != NEM_DATASET_NAME or provenance.get("dataset_source") != NEM_DATASET_SOURCE:
            raise ValueError("dataset provenance is incompatible")
        if result.get("artifact_name") != NEM_H2_ARTIFACT_NAMES["classification"]:
            raise ValueError("artifact_name is not the NEM H2 Classification artifact")


classification_service_client = ClassificationServiceClient()
