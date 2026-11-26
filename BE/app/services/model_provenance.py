"""Validation helpers for safe model-build metadata stored in ModelRun JSONB."""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import PurePath
from typing import Any


MODEL_METADATA_FIELDS = {
    "model_type",
    "model_name",
    "artifact_name",
    "artifact_format",
    "artifact_version",
    "contract_version",
    "horizon_days",
    "feature_schema_version",
    "python_version",
    "sklearn_version",
    "trained_at",
    "model_parameters",
}
_CLUSTERING_MODEL_METADATA_FIELDS = MODEL_METADATA_FIELDS - {
    "horizon_days",
    "feature_schema_version",
}
_SENSITIVE_KEY_PARTS = ("secret", "password", "token", "credential", "database_url")


class ModelProvenanceError(ValueError):
    """Training metadata is incomplete, malformed, or contains sensitive fields."""


def _validate_safe_json(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ModelProvenanceError("model_parameters must contain only finite values")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or any(part in key.lower() for part in _SENSITIVE_KEY_PARTS):
                raise ModelProvenanceError("model provenance must not include sensitive fields")
            _validate_safe_json(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _validate_safe_json(child)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ModelProvenanceError("model_parameters must be JSON-compatible")


def merge_training_model_provenance(
    dataset_provenance: dict[str, Any],
    model_metadata: Any,
    *,
    expected_model_type: str,
) -> dict[str, Any]:
    """Attach a strict build-metadata object without changing dataset identity keys."""
    if expected_model_type not in {"clustering", "prediction", "classification"}:
        raise ModelProvenanceError("model type is unsupported")
    expected_fields = (
        _CLUSTERING_MODEL_METADATA_FIELDS
        if expected_model_type == "clustering"
        else MODEL_METADATA_FIELDS
    )
    if not isinstance(model_metadata, dict) or set(model_metadata) != expected_fields:
        raise ModelProvenanceError("model build metadata is missing required fields")
    if model_metadata.get("model_type") != expected_model_type:
        raise ModelProvenanceError("model build metadata has the wrong model type")
    for field in ("model_name", "artifact_name", "python_version", "sklearn_version", "trained_at"):
        if not isinstance(model_metadata.get(field), str) or not model_metadata[field].strip():
            raise ModelProvenanceError(f"model build metadata field {field!r} is invalid")
    artifact_name = model_metadata["artifact_name"]
    if (PurePath(artifact_name).name != artifact_name
            or "/" in artifact_name or "\\" in artifact_name):
        raise ModelProvenanceError("artifact_name must be a filename, not a path")
    if model_metadata.get("artifact_format") != "joblib":
        raise ModelProvenanceError("artifact format is unsupported")
    version = model_metadata.get("artifact_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ModelProvenanceError("artifact_version is invalid")
    contract_version = model_metadata.get("contract_version")
    if isinstance(contract_version, bool) or not isinstance(contract_version, int) or contract_version < 1:
        raise ModelProvenanceError("contract_version is invalid")
    if expected_model_type in {"prediction", "classification"}:
        horizon_days = model_metadata.get("horizon_days")
        if isinstance(horizon_days, bool) or not isinstance(horizon_days, int) or horizon_days != 2:
            raise ModelProvenanceError("horizon_days is invalid")
        feature_schema_version = model_metadata.get("feature_schema_version")
        if feature_schema_version != "nem_daily_demand_h2_v1":
            raise ModelProvenanceError("feature_schema_version is invalid")
    try:
        timestamp = datetime.fromisoformat(model_metadata["trained_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ModelProvenanceError("trained_at must be an ISO timestamp") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ModelProvenanceError("trained_at must include a timezone")
    parameters = model_metadata.get("model_parameters")
    if not isinstance(parameters, dict):
        raise ModelProvenanceError("model_parameters must be an object")
    _validate_safe_json(parameters)
    return {**dataset_provenance, "model": model_metadata.copy()}
