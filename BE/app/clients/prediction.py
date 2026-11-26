import json
import logging
import math
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE
from app.services.nem_ml_contract import NEM_H2_ARTIFACT_NAMES


logger = logging.getLogger(__name__)
_DIAGNOSTIC_REQUEST_ID: ContextVar[str | None] = ContextVar(
    "prediction_diagnostic_request_id", default=None
)

_DIAGNOSTIC_FIELDS = (
    "stage", "model_name", "target", "unit", "network_code", "metric", "interval",
    "forecast_horizon_days", "feature_schema_version", "dataset_id", "dataset_name",
    "dataset_source", "observation_start", "observation_end", "training_start",
    "training_end", "training_sample_count", "training_data_fingerprint", "feature_names",
    "validation", "shuffle", "fold_count", "folds", "overall", "random_forest",
    "persistence_baseline", "seasonal_naive_7d_baseline", "validation_sample_count",
    "mae_mw", "rmse_mw", "mape_pct", "artifact_name", "model_type", "artifact_format",
    "artifact_version", "contract_version", "horizon_days", "python_version",
    "sklearn_version", "trained_at", "model_parameters",
)


@contextmanager
def prediction_diagnostic_context(request_id: str):
    """Attach a Gateway-generated ID to logs made during one client call."""
    token = _DIAGNOSTIC_REQUEST_ID.set(request_id)
    try:
        yield
    finally:
        _DIAGNOSTIC_REQUEST_ID.reset(token)


def _diagnostic_request_id() -> str:
    return _DIAGNOSTIC_REQUEST_ID.get() or uuid4().hex


def safe_prediction_validation_details(exc: BaseException) -> tuple[str, str]:
    message = str(exc)
    fields = [
        field for field in _DIAGNOSTIC_FIELDS
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(field)}(?![A-Za-z0-9_])", message)
    ]
    lowered = message.lower()
    if "required" in lowered:
        kind = "required"
    elif "missing" in lowered:
        kind = "missing"
    elif any(marker in lowered for marker in ("invalid", "incompatible", "must be", "unsupported")):
        kind = "invalid"
    else:
        kind = "contract"
    return ",".join(fields) if fields else "none", kind


def _log_prediction_diagnostic(
    *, request_id: str, operation: str, stage: str, exc: BaseException,
    status_code: int | None = None, validation: bool = False,
) -> None:
    fields, kind = safe_prediction_validation_details(exc) if validation else ("none", "none")
    logger.warning(
        "Prediction diagnostic request_id=%s operation=%s stage=%s exception_class=%s "
        "status_code=%s validation_fields=%s validation_kind=%s",
        request_id, operation, stage, type(exc).__name__, status_code or "none", fields, kind,
    )


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

    def train_nem(self, payload: dict) -> dict:
        return self._post_payload("nem/train", payload, expected_stage="training")

    def run_nem(self, payload: dict) -> dict:
        result = self._post_payload("nem/run", payload, expected_stage="forecast")
        forecast = payload.get("forecast")
        if not isinstance(forecast, dict) or (
            result.get("forecast_date") != forecast.get("forecast_date")
            or result.get("cutoff_date") != forecast.get("cutoff_date")
            or result.get("as_of_date") != forecast.get("as_of_date")
        ):
            raise PredictionServiceUnavailable("Prediction Service returned dates inconsistent with the request")
        return result

    def _post(self, operation: str, records: list[dict], *, expected_stage: str) -> dict:
        return self._post_payload(operation, {"records": records}, expected_stage=expected_stage)

    def _post_payload(self, operation: str, payload: dict, *, expected_stage: str) -> dict:
        diagnostic_id = _diagnostic_request_id()
        base_url = (
            self._base_url
            or os.getenv("PREDICTION_SERVICE_URL", "http://127.0.0.1:8103")
        ).rstrip("/")
        secret = self._secret if self._secret is not None else os.getenv("PREDICTION_SERVICE_SECRET", "")
        try:
            timeout_seconds = self._resolve_timeout()
        except PredictionServiceUnavailable as exc:
            _log_prediction_diagnostic(
                request_id=diagnostic_id, operation=operation, stage="client_http", exc=exc,
            )
            raise
        if len(secret.encode("utf-8")) < 32:
            exc = PredictionServiceUnavailable("Prediction Service is not configured")
            _log_prediction_diagnostic(
                request_id=diagnostic_id, operation=operation, stage="client_http", exc=exc,
            )
            raise exc

        try:
            request_body = json.dumps(payload, allow_nan=False).encode("utf-8")
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
        logger.info(
            "Calling Prediction Service: request_id=%s operation=%s",
            diagnostic_id, operation,
        )

        try:
            with self._opener(request, timeout=timeout_seconds) as response:
                status_code = response.status
                response_body = response.read()
        except HTTPError as exc:
            _log_prediction_diagnostic(
                request_id=diagnostic_id, operation=operation, stage="client_http",
                exc=exc, status_code=exc.code,
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
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            _log_prediction_diagnostic(
                request_id=diagnostic_id, operation=operation, stage="client_http", exc=exc,
            )
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
            exc = RuntimeError("unexpected HTTP status")
            _log_prediction_diagnostic(
                request_id=diagnostic_id, operation=operation, stage="client_http",
                exc=exc, status_code=status_code,
            )
            raise PredictionServiceUnavailable("Prediction Service returned an unexpected status")

        try:
            result = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            _log_prediction_diagnostic(
                request_id=diagnostic_id, operation=operation, stage="response_json", exc=exc,
            )
            raise PredictionServiceUnavailable("Prediction Service returned an invalid response") from exc
        try:
            self._validate_response(result, operation=operation, expected_stage=expected_stage)
        except (TypeError, ValueError, KeyError, OverflowError) as exc:
            _log_prediction_diagnostic(
                request_id=diagnostic_id, operation=operation, stage="response_validation",
                exc=exc, validation=True,
            )
            raise PredictionServiceUnavailable(
                "Prediction Service returned an incompatible response"
            ) from exc
        return result

    def _resolve_timeout(self) -> float:
        configured = (
            self._timeout_seconds
            if self._timeout_seconds is not None
            else os.getenv("PREDICTION_SERVICE_TIMEOUT_SECONDS", "120")
        )
        try:
            if isinstance(configured, bool):
                raise ValueError
            timeout = float(configured)
        except (TypeError, ValueError, OverflowError) as exc:
            raise PredictionServiceUnavailable(
                "Prediction Service timeout configuration is invalid"
            ) from exc
        if not math.isfinite(timeout) or timeout <= 0:
            raise PredictionServiceUnavailable(
                "Prediction Service timeout configuration is invalid"
            )
        return timeout

    @classmethod
    def _validate_response(cls, result: object, *, operation: str, expected_stage: str) -> None:
        if not isinstance(result, dict) or result.get("stage") != expected_stage:
            raise ValueError("unexpected response envelope")
        if not isinstance(result.get("model_name"), str) or not result["model_name"].strip():
            raise ValueError("model_name is required")
        cls._validate_finite_tree(result)

        if operation == "nem/train":
            cls._validate_nem_training(result)
        elif operation == "nem/run":
            cls._validate_nem_forecast(result)
        elif expected_stage == "training":
            cls._validate_legacy_training(result)
        else:
            cls._validate_legacy_forecast(result)

    @classmethod
    def _validate_finite_tree(cls, value: object) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("response contains a non-finite number")
        if isinstance(value, dict):
            for child in value.values():
                cls._validate_finite_tree(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                cls._validate_finite_tree(child)

    @staticmethod
    def _require_text(result: dict, field: str) -> str:
        value = result.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} is required")
        return value

    @staticmethod
    def _require_number(result: dict, field: str, *, nonnegative: bool = False, nullable: bool = False) -> None:
        value = result.get(field)
        if nullable and value is None:
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{field} must be a finite number")
        if nonnegative and value < 0:
            raise ValueError(f"{field} must be nonnegative")

    @staticmethod
    def _require_count(result: dict, field: str, *, positive: bool = False) -> None:
        value = result.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < (1 if positive else 0):
            raise ValueError(f"{field} must be a valid count")

    @classmethod
    def _validate_nem_metrics(cls, metrics: object) -> None:
        if not isinstance(metrics, dict):
            raise ValueError("validation metrics are required")
        for key in ("mae_mw", "rmse_mw", "mape_pct"):
            cls._require_number(metrics, key, nonnegative=True, nullable=(key == "mape_pct"))

    @classmethod
    def _validate_nem_training(cls, result: dict) -> None:
        for field, expected in (("target", "daily_demand"), ("unit", "MW"),
                                ("network_code", "NEM"), ("metric", "demand"),
                                ("interval", "1d"), ("forecast_horizon_days", 2),
                                ("feature_schema_version", "nem_daily_demand_h2_v1")):
            if result.get(field) != expected:
                raise ValueError(f"{field} has an incompatible value")
        dataset_id = result.get("dataset_id")
        if isinstance(dataset_id, bool) or not isinstance(dataset_id, int) or dataset_id <= 0:
            raise ValueError("dataset_id is invalid")
        for field in ("dataset_name", "dataset_source", "observation_start", "observation_end",
                      "training_start", "training_end"):
            cls._require_text(result, field)
        if (result["dataset_name"] != NEM_DATASET_NAME
                or result["dataset_source"] != NEM_DATASET_SOURCE):
            raise ValueError("training dataset provenance is incompatible")
        cls._require_count(result, "training_sample_count", positive=True)
        cls._require_fingerprint(result, "training_data_fingerprint")
        if (not isinstance(result.get("feature_names"), list) or not result["feature_names"]
                or not all(isinstance(name, str) and name for name in result["feature_names"])):
            raise ValueError("feature_names are required")
        if result.get("feature_schema_version") != "nem_daily_demand_h2_v1":
            raise ValueError("feature schema version is incompatible")
        validation = result.get("validation")
        if not isinstance(validation, dict) or validation.get("shuffle") is not False:
            raise ValueError("chronological validation metrics are required")
        cls._require_count(validation, "fold_count", positive=True)
        folds = validation.get("folds")
        if not isinstance(folds, list) or len(folds) != validation["fold_count"]:
            raise ValueError("validation folds are invalid")
        overall = validation.get("overall")
        if not isinstance(overall, dict):
            raise ValueError("overall validation metrics are required")
        for name in ("random_forest", "persistence_baseline", "seasonal_naive_7d_baseline"):
            cls._validate_nem_metrics(overall.get(name))
        for fold in folds:
            if not isinstance(fold, dict):
                raise ValueError("validation fold is invalid")
            cls._require_count(fold, "validation_sample_count", positive=True)
            for name in ("random_forest", "persistence_baseline", "seasonal_naive_7d_baseline"):
                cls._validate_nem_metrics(fold.get(name))
        if cls._require_text(result, "artifact_name") != NEM_H2_ARTIFACT_NAMES["prediction"]:
            raise ValueError("artifact_name is not the NEM H2 Prediction artifact")

    @classmethod
    def _validate_nem_forecast(cls, result: dict) -> None:
        for field, expected in (("target", "daily_demand"), ("unit", "MW"),
                                ("network_code", "NEM"), ("metric", "demand"),
                                ("interval", "1d")):
            if result.get(field) != expected:
                raise ValueError(f"{field} has an incompatible value")
        cls._require_text(result, "forecast_date")
        forecast_date = date.fromisoformat(result["forecast_date"])
        cls._require_text(result, "as_of_date")
        as_of_date = date.fromisoformat(result["as_of_date"])
        cls._require_text(result, "cutoff_date")
        cutoff_date = date.fromisoformat(result["cutoff_date"])
        if result.get("horizon_days") != 2 or result.get("forecast_status") != "ready":
            raise ValueError("forecast horizon or status is incompatible")
        if forecast_date != cutoff_date + timedelta(days=2) or cutoff_date != as_of_date - timedelta(days=1) or forecast_date != as_of_date + timedelta(days=1):
            raise ValueError("forecast date does not match the two-day horizon")
        cls._require_number(result, "predicted_demand", nonnegative=True)
        cls._require_text(result, "last_observed_date")
        if date.fromisoformat(result["last_observed_date"]) != cutoff_date:
            raise ValueError("last observation does not match cutoff date")
        cls._require_fingerprint(result, "training_data_fingerprint")
        cls._require_fingerprint(result, "run_data_fingerprint")
        observed_at = cls._require_text(result, "last_observed_at")
        parsed_timestamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() is None:
            raise ValueError("last_observed_at must include a timezone")
        provenance = result.get("dataset_provenance")
        if not isinstance(provenance, dict):
            raise ValueError("dataset provenance is required")
        provenance_id = provenance.get("dataset_id")
        if isinstance(provenance_id, bool) or not isinstance(provenance_id, int) or provenance_id <= 0:
            raise ValueError("dataset provenance has an invalid dataset_id")
        for field in ("dataset_name", "dataset_source"):
            value = provenance.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"dataset provenance is missing {field}")
        if (provenance["dataset_name"] != NEM_DATASET_NAME
                or provenance["dataset_source"] != NEM_DATASET_SOURCE):
            raise ValueError("dataset provenance is incompatible")
        for field, expected in (("network_code", "NEM"), ("metric", "demand"),
                                ("interval", "1d"), ("unit", "MW")):
            if provenance.get(field) != expected:
                raise ValueError(f"dataset provenance has an incompatible {field}")
        if cls._require_text(result, "artifact_name") != NEM_H2_ARTIFACT_NAMES["prediction"]:
            raise ValueError("artifact_name is not the NEM H2 Prediction artifact")

    @classmethod
    def _require_fingerprint(cls, result: dict, field: str) -> None:
        value = cls._require_text(result, field)
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(f"{field} is invalid")

    @classmethod
    def _validate_legacy_metrics(cls, value: object) -> None:
        if not isinstance(value, dict):
            raise ValueError("metrics are required")
        for field in ("mae", "rmse", "mape_pct", "r2"):
            cls._require_number(value, field, nullable=(field == "mape_pct"))

    @classmethod
    def _validate_legacy_training(cls, result: dict) -> None:
        cls._require_count(result, "window_months", positive=True)
        cls._require_count(result, "training_sample_count", positive=True)
        cls._require_count(result, "holdout_sample_count", positive=True)
        cls._require_text(result, "holdout_start_month")
        cls._require_text(result, "holdout_end_month")
        cls._validate_legacy_metrics(result.get("holdout_metrics"))
        cls._validate_legacy_metrics(result.get("seasonal_naive_metrics"))
        cls._require_text(result, "artifact_name")

    @classmethod
    def _validate_legacy_forecast(cls, result: dict) -> None:
        cls._require_text(result, "forecast_month")
        cls._require_number(result, "predicted_demand", nonnegative=True)
        if result.get("unit") != "TWh":
            raise ValueError("forecast unit is incompatible")
        cls._require_text(result, "trained_through_month")
        cls._require_count(result, "window_months", positive=True)
        cls._require_text(result, "artifact_name")


prediction_service_client = PredictionServiceClient()
