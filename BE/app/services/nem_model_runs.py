"""SQL predicates for isolating NEM model-run history from legacy runs."""

from sqlalchemy import and_, func, or_

from app.db.models import ModelRun
from app.services.nem_ml_contract import (
    NEM_FEATURE_SCHEMA_VERSION,
    NEM_FORECAST_HORIZON_DAYS,
    NEM_H2_ARTIFACT_NAMES,
)
from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE

NEM_ML_MODEL_TYPES = ("clustering", "prediction", "classification")


def nem_model_run_filter(
    model_type: str,
    *,
    metric: str | None = None,
    unit: str | None = None,
):
    """Require an explicit, matching NEM dataset provenance in JSONB."""
    provenance = ModelRun.parameters["provenance"]
    predicates = [
        ModelRun.model_type == model_type,
        provenance["dataset_name"].astext == NEM_DATASET_NAME,
        provenance["dataset_source"].astext == NEM_DATASET_SOURCE,
        provenance["network_code"].astext == "NEM",
        provenance["interval"].astext == "1d",
    ]
    if metric is not None:
        predicates.append(provenance["metric"].astext == metric)
    if unit is not None:
        predicates.append(provenance["unit"].astext == unit)
    return and_(*predicates)


def nem_h2_model_run_filter(model_type: str):
    """Match NEM fixed-horizon H2 runs; legacy NEM runs are not substitutes."""
    if model_type not in {"prediction", "classification"}:
        raise ValueError("H2 run filtering is supported only for prediction and classification")
    provenance = ModelRun.parameters["provenance"]
    dataset_id = provenance["dataset_id"]
    expected_artifact = NEM_H2_ARTIFACT_NAMES[model_type]
    return and_(
        nem_model_run_filter(model_type, metric="demand", unit="MW"),
        provenance["horizon_days"].astext == str(NEM_FORECAST_HORIZON_DAYS),
        provenance["feature_schema_version"].astext == NEM_FEATURE_SCHEMA_VERSION,
        func.jsonb_typeof(dataset_id) == "number",
        dataset_id.astext.op("~")(r"^[1-9][0-9]*$"),
        or_(
            ModelRun.status != "completed",
            ModelRun.metrics["artifact_name"].astext == expected_artifact,
        ),
    )


def nem_ml_model_run_filter(model_type: str | None = None):
    """Filter active NEM ML ModelRuns, requiring H2 for daily demand models."""
    if model_type is not None:
        if model_type not in NEM_ML_MODEL_TYPES:
            raise ValueError("unsupported ML model type")
        if model_type in {"prediction", "classification"}:
            return nem_h2_model_run_filter(model_type)
        return nem_model_run_filter(model_type)

    return or_(
        nem_model_run_filter("clustering"),
        nem_h2_model_run_filter("prediction"),
        nem_h2_model_run_filter("classification"),
    )
