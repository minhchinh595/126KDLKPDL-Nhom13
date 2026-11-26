from datetime import datetime, timezone
from datetime import date
import platform
from types import SimpleNamespace

import pytest
import sklearn
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.db.models import ModelRun
from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE
from app.services.nem_ml_contract import NEM_H2_ARTIFACT_NAMES


MODULES = [
    ("clustering", "run", None, None),
    ("prediction", "forecast", "demand", "MW"),
    ("classification", "forecast", "demand", "MW"),
]


def _provenance(*, dataset_id=4, name=NEM_DATASET_NAME, source=NEM_DATASET_SOURCE, network="NEM", interval="1d", metric="demand", unit="MW", horizon_days=2, feature_schema_version="nem_daily_demand_h2_v1"):
    return {
        "dataset_id": dataset_id,
        "dataset_name": name,
        "dataset_source": source,
        "network_code": network,
        "interval": interval,
        "metric": metric,
        "unit": unit,
        "horizon_days": horizon_days,
        "feature_schema_version": feature_schema_version,
    }


def _run(model_type, run_id, provenance, *, stage, created_minute, cutoff_date="2026-11-25", forecast_date="2026-11-27", artifact_name="default"):
    metrics = {"stage": stage, "marker": run_id, "cutoff_date": cutoff_date, "forecast_date": forecast_date}
    if model_type in NEM_H2_ARTIFACT_NAMES:
        if artifact_name == "default":
            artifact_name = NEM_H2_ARTIFACT_NAMES[model_type]
        if artifact_name is not None:
            metrics["artifact_name"] = artifact_name
    return ModelRun(
        id=run_id,
        model_type=model_type,
        status="completed",
        created_at=datetime(2026, 11, 25, 0, created_minute, tzinfo=timezone.utc),
        parameters={"stage": stage, **({"provenance": provenance} if provenance is not None else {})},
        metrics=metrics,
    )


class FilteringSession:
    """Small fake that applies the NEM identity and query stage to stored rows."""

    def __init__(self, rows):
        self.rows = rows

    @staticmethod
    def _matches_identity(row, model_type, metric, unit, horizon_days=None, feature_schema_version=None):
        provenance = (row.parameters or {}).get("provenance") or {}
        dataset_id = provenance.get("dataset_id")
        valid = (
            row.model_type == model_type
            and type(dataset_id) is int and dataset_id > 0
            and provenance.get("dataset_name") == NEM_DATASET_NAME
            and provenance.get("dataset_source") == NEM_DATASET_SOURCE
            and provenance.get("network_code") == "NEM"
            and provenance.get("interval") == "1d"
        )
        if metric is not None:
            valid = valid and provenance.get("metric") == metric
        if unit is not None:
            valid = valid and provenance.get("unit") == unit
        if horizon_days is not None:
            valid = valid and provenance.get("horizon_days") == horizon_days
        if feature_schema_version is not None:
            valid = valid and provenance.get("feature_schema_version") == feature_schema_version
        if row.model_type in NEM_H2_ARTIFACT_NAMES and row.status == "completed":
            valid = valid and (row.metrics or {}).get("artifact_name") == NEM_H2_ARTIFACT_NAMES[row.model_type]
        return valid

    def _matching(self, statement):
        compiled = statement.compile(dialect=postgresql.dialect())
        params = compiled.params
        sql = str(compiled)
        model_type = next(value for key, value in params.items() if key.startswith("model_type_"))
        provenance_keys = [
            (key, value) for key, value in params.items()
            if key.startswith("param_") and key.removeprefix("param_").isdigit()
        ]
        metric = "demand" if any(value == "demand" for _, value in provenance_keys) else None
        unit = "MW" if any(value == "MW" for _, value in provenance_keys) else None
        h2_filter = "nem_daily_demand_h2_v1" in params.values()
        horizon_days = 2 if h2_filter else None
        feature_schema_version = "nem_daily_demand_h2_v1" if h2_filter else None
        # Verify the SQL statement itself carries all required JSONB provenance terms.
        for field in ("dataset_name", "dataset_source", "network_code", "interval"):
            assert field in params.values()
        expected = [row for row in self.rows if self._matches_identity(row, model_type, metric, unit, horizon_days, feature_schema_version)]
        run_id = next((value for key, value in params.items() if key.startswith("id_")), None)
        if run_id is not None:
            expected = [row for row in expected if row.id == run_id]
        status = next((value for key, value in params.items() if key.startswith("status_")), None)
        if status is not None and "model_runs.status =" in sql:
            expected = [row for row in expected if row.status == status]
        stage = next((value for key, value in params.items() if key.startswith("param_") and value in {"run", "forecast"}), None)
        if stage is not None and "metrics ->>" in sql:
            expected = [row for row in expected if (row.metrics or {}).get("stage") == stage]
        metric_fields = [value for key, value in params.items() if key.startswith("metrics_")]
        requested_dates = [value for key, value in params.items() if key.startswith("param_") and isinstance(value, str) and len(value) == 10 and value[4:5] == "-" and value[7:8] == "-"]
        if {"cutoff_date", "forecast_date"}.issubset(metric_fields):
            expected = [
                row for row in expected
                if (row.metrics or {}).get("cutoff_date") in requested_dates
                and (row.metrics or {}).get("forecast_date") in requested_dates
            ]
        expected = sorted(expected, key=lambda row: row.id, reverse=True)
        offset = getattr(statement._offset, "value", statement._offset)
        limit = getattr(statement._limit, "value", statement._limit)
        if offset is not None:
            expected = expected[offset:]
        if limit is not None:
            expected = expected[:limit]
        return expected

    def execute(self, statement):
        rows = self._matching(statement)
        return SimpleNamespace(scalar_one_or_none=lambda: rows[0] if rows else None)

    def scalar(self, statement):
        return len(self._matching(statement))

    def scalars(self, statement):
        return SimpleNamespace(all=lambda: self._matching(statement))


class RecordingSession(FilteringSession):
    def __init__(self):
        super().__init__([])
        self.next_id = 100

    def add(self, row):
        self.next_id += 1
        row.id = self.next_id
        row.created_at = datetime(2026, 11, 26, 0, self.next_id % 60, tzinfo=timezone.utc)
        self.rows.append(row)

    def commit(self):
        pass

    def rollback(self):
        pass

    def refresh(self, row):
        pass


def _valid_h2_payload(*, ready=True):
    return {
        "dataset_id": 4,
        "dataset_name": NEM_DATASET_NAME,
        "dataset_source": NEM_DATASET_SOURCE,
        "network_code": "NEM",
        "metric": "demand",
        "interval": "1d",
        "unit": "MW",
        "feature_names": ["demand_at_cutoff"],
        "feature_units": {"demand_at_cutoff": "MW"},
        "observation_start": "2025-11-26",
        "observation_end": "2026-11-25",
        "observation_count": 365,
        "training_start": "2025-12-23",
        "training_end": "2026-11-23",
        "training_sample_count": 336,
        "excluded_sample_count": 0,
        "exclusion_reasons": {},
        "missing_dates": [],
        "data_fingerprint": "a" * 64,
        "horizon_days": 2,
        "feature_schema_version": "nem_daily_demand_h2_v1",
        "forecast_date": "2026-11-27",
        "cutoff_date": "2026-11-25",
        "forecast_status": "ready" if ready else "not_ready",
        "forecast": {"forecast_date": "2026-11-27"} if ready else None,
        "forecast_message": "Required cutoff observation is not available" if not ready else None,
        "as_of_date": "2026-11-26",
        "last_observed_date": "2026-11-25",
    }


@pytest.mark.parametrize("model_type,action", [("prediction", "train"), ("prediction", "run"), ("classification", "train"), ("classification", "run")])
def test_failed_h2_train_and_run_are_visible_in_matching_history(monkeypatch, model_type, action):
    from app.api.routes import classification, prediction
    from app.clients.classification import ClassificationServiceConflict
    from app.clients.prediction import PredictionServiceConflict

    route = prediction if model_type == "prediction" else classification
    db = RecordingSession()
    payload = _valid_h2_payload()
    monkeypatch.setattr(route, f"_load_nem_{'prediction' if model_type == 'prediction' else 'classification'}_payload", lambda session: payload)
    client = route.prediction_service_client if model_type == "prediction" else route.classification_service_client
    method = "train_nem" if action == "train" else "run_nem"
    error_type = PredictionServiceConflict if model_type == "prediction" else ClassificationServiceConflict

    def reject_request(request_payload):
        raise error_type("artifact unavailable")

    monkeypatch.setattr(client, method, reject_request)
    endpoint = route.train_prediction_model if model_type == "prediction" and action == "train" else (
        route.run_prediction if model_type == "prediction" else (
            route.train_classification_model if action == "train" else route.run_classification
        )
    )
    with pytest.raises(HTTPException) as error:
        endpoint(db=db, _=None)
    assert error.value.status_code == 409
    assert len(db.rows) == 1
    failed = db.rows[0]
    assert failed.model_type == model_type
    assert failed.status == "failed"
    assert failed.parameters["stage"] == ("training" if action == "train" else "forecast")
    assert failed.error_message == "artifact unavailable"
    provenance = failed.parameters["provenance"]
    assert provenance["dataset_id"] == 4
    assert provenance["dataset_name"] == NEM_DATASET_NAME
    assert provenance["dataset_source"] == NEM_DATASET_SOURCE
    assert provenance["network_code"] == "NEM"
    assert provenance["metric"] == "demand"
    assert provenance["interval"] == "1d"
    assert provenance["unit"] == "MW"
    assert provenance["horizon_days"] == 2
    assert provenance["feature_schema_version"] == "nem_daily_demand_h2_v1"

    history = route.list_prediction_runs(page=1, page_size=10, db=db) if model_type == "prediction" else route.list_classification_runs(page=1, page_size=10, db=db)
    assert history["total"] == 1
    assert history["items"][0]["id"] == failed.id
    assert history["items"][0]["status"] == "failed"


@pytest.mark.parametrize("model_type", ["prediction", "classification"])
def test_failed_h2_history_rejects_missing_or_mismatched_provenance(model_type):
    from app.api.routes import classification, prediction

    route = prediction if model_type == "prediction" else classification
    valid = _provenance()
    rows = [
        _run(model_type, 1, None, stage="forecast", created_minute=1),
        _run(model_type, 8, {key: value for key, value in _provenance().items() if key != "dataset_id"}, stage="forecast", created_minute=8),
        _run(model_type, 9, _provenance(dataset_id=None), stage="forecast", created_minute=9),
        _run(model_type, 10, _provenance(dataset_id=0), stage="forecast", created_minute=10),
        _run(model_type, 11, _provenance(dataset_id=-1), stage="forecast", created_minute=11),
        _run(model_type, 2, _provenance(name="Legacy VNM"), stage="forecast", created_minute=2),
        _run(model_type, 3, _provenance(source="https://example.invalid/other"), stage="forecast", created_minute=3),
        _run(model_type, 4, _provenance(network="NSW1"), stage="forecast", created_minute=4),
        _run(model_type, 5, _provenance(interval="5m"), stage="forecast", created_minute=5),
        _run(model_type, 6, _provenance(horizon_days=1, feature_schema_version="nem_daily_demand_h1_v1"), stage="forecast", created_minute=6),
        _run(model_type, 7, valid, stage="forecast", created_minute=7, artifact_name=None),
    ]
    for row in rows:
        row.status = "failed"
    db = FilteringSession(rows)
    history = route.list_prediction_runs(page=1, page_size=20, db=db) if model_type == "prediction" else route.list_classification_runs(page=1, page_size=20, db=db)
    assert history["total"] == 1
    assert [item["id"] for item in history["items"]] == [7]


@pytest.mark.parametrize("model_type", ["prediction", "classification"])
def test_not_ready_run_returns_409_without_recording_model_run(monkeypatch, model_type):
    from app.api.routes import classification, prediction

    route = prediction if model_type == "prediction" else classification
    payload = _valid_h2_payload(ready=False)
    db = RecordingSession()
    loader_name = "_load_nem_prediction_payload" if model_type == "prediction" else "_load_nem_classification_payload"
    monkeypatch.setattr(route, loader_name, lambda session: payload)
    endpoint = route.run_prediction if model_type == "prediction" else route.run_classification

    with pytest.raises(HTTPException) as error:
        endpoint(db=db, _=None)
    assert error.value.status_code == 409
    assert error.value.detail["forecast_status"] == "not_ready"
    assert db.rows == []


@pytest.mark.parametrize("model_type,stage,metric,unit", MODULES)
def test_latest_and_history_only_include_matching_nem_runs(monkeypatch, model_type, stage, metric, unit):
    from app.api.routes import classification, clustering, prediction

    route = {"clustering": clustering, "prediction": prediction, "classification": classification}[model_type]
    if model_type in {"prediction", "classification"}:
        monkeypatch.setattr(route, "nem_forecast_dates", lambda: (date(2026, 11, 26), date(2026, 11, 25), date(2026, 11, 27)))
    latest = getattr(route, f"get_latest_{model_type}")
    list_runs = getattr(route, f"list_{model_type}_runs")
    run_filter = route.nem_h2_model_run_filter if model_type in {"prediction", "classification"} else route.nem_model_run_filter
    rows = [
        _run(model_type, 1, _provenance(), stage=stage, created_minute=1),
        _run(model_type, 2, _provenance(), stage=stage, created_minute=2),
        *([] if model_type == "clustering" else [
            _run(model_type, 14, _provenance(), stage=stage, created_minute=14, artifact_name="electricity_nem_daily_demand_rf.joblib" if model_type == "prediction" else "electricity_nem_daily_demand_classifier.joblib"),
            _run(model_type, 15, _provenance(), stage=stage, created_minute=15, artifact_name=None),
            _run(model_type, 16, _provenance(), stage=stage, created_minute=16, artifact_name=NEM_H2_ARTIFACT_NAMES["classification" if model_type == "prediction" else "prediction"]),
        ]),
            _run(model_type, 3, _provenance(horizon_days=1, feature_schema_version="nem_daily_demand_h1_v1") if model_type != "clustering" else _provenance(), stage=stage, created_minute=3),
        _run(model_type, 4, _provenance(name="Legacy VNM"), stage=stage, created_minute=4),
        _run(model_type, 5, None, stage=stage, created_minute=5),
        _run(model_type, 6, _provenance(network="NSW1"), stage=stage, created_minute=6),
        _run(model_type, 7, _provenance(interval="5m"), stage=stage, created_minute=7),
        _run(model_type, 8, _provenance(source="https://example.invalid/other"), stage=stage, created_minute=8),
        *([] if metric is None else [
            _run(model_type, 9, _provenance(metric="price"), stage=stage, created_minute=9),
            _run(model_type, 10, _provenance(unit="TWh"), stage=stage, created_minute=10),
        ]),
        _run("classification" if model_type != "classification" else "prediction", 11, _provenance(), stage=stage, created_minute=11),
            *([] if model_type == "clustering" else [
                _run(model_type, 12, _provenance(), stage=stage, created_minute=12, cutoff_date="2026-11-23", forecast_date="2026-11-25"),
            ]),
    ]
    if model_type in {"prediction", "classification"}:
        failed_h2 = _run(model_type, 13, _provenance(), stage=stage, created_minute=13, artifact_name=None)
        failed_h2.status = "failed"
        rows.append(failed_h2)
    db = FilteringSession(rows)

    statement = select(ModelRun).where(run_filter(model_type, metric=metric, unit=unit) if model_type == "clustering" else run_filter(model_type))
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "model_runs.parameters" in str(compiled)
    assert "provenance" in compiled.params.values()
    assert NEM_DATASET_NAME in compiled.params.values()
    assert NEM_DATASET_SOURCE in compiled.params.values()
    if model_type in {"prediction", "classification"}:
        assert "jsonb_typeof" in str(compiled)
        assert "~" in str(compiled)
        assert "number" in compiled.params.values()
        assert r"^[1-9][0-9]*$" in compiled.params.values()
        assert NEM_H2_ARTIFACT_NAMES[model_type] in compiled.params.values()

    latest_result = latest(db)
    assert latest_result["id"] == (3 if model_type == "clustering" else 2)
    history = list_runs(page=1, page_size=20, db=db)
    expected_history_ids = [3, 2, 1] if model_type == "clustering" else [13, 12, 2, 1]
    assert history["total"] == len(expected_history_ids)
    assert [item["id"] for item in history["items"]] == expected_history_ids
    # These fixture runs use the pre-2.7D dataset provenance shape without a model metadata block.
    assert "model" not in history["items"][0]["parameters"]["provenance"]
    detail = getattr(route, f"get_{model_type}_run")
    expected_detail_id = 3 if model_type == "clustering" else 2
    assert detail(expected_detail_id, db=db)["id"] == expected_detail_id
    rejected_id = 4 if model_type == "clustering" else 3
    with pytest.raises(HTTPException) as detail_error:
        detail(rejected_id, db=db)
    assert detail_error.value.status_code == 404


@pytest.mark.parametrize("model_type,stage,metric,unit", MODULES)
def test_no_nem_run_returns_existing_empty_contract_without_vnm_fallback(monkeypatch, model_type, stage, metric, unit):
    from app.api.routes import classification, clustering, prediction

    route = {"clustering": clustering, "prediction": prediction, "classification": classification}[model_type]
    if model_type in {"prediction", "classification"}:
        monkeypatch.setattr(route, "nem_forecast_dates", lambda: (date(2026, 11, 26), date(2026, 11, 25), date(2026, 11, 27)))
    latest = getattr(route, f"get_latest_{model_type}")
    list_runs = getattr(route, f"list_{model_type}_runs")
    db = FilteringSession([
        _run(model_type, 20, _provenance(name="Legacy VNM"), stage=stage, created_minute=5),
        _run(model_type, 21, None, stage=stage, created_minute=6),
        *([] if model_type == "clustering" else [_run(model_type, 22, _provenance(horizon_days=1, feature_schema_version="nem_daily_demand_h1_v1"), stage=stage, created_minute=7)]),
    ])

    with pytest.raises(HTTPException) as error:
        latest(db)
    assert error.value.status_code == 404
    history = list_runs(page=1, page_size=20, db=db)
    assert history["items"] == []
    assert history["total"] == 0


def test_nem_model_artifact_defaults_are_distinct(monkeypatch):
    from app.clustering import nem_kmeans
    from app.prediction import nem_model
    from app.classification import nem_classifier

    for variable in (
        "NEM_CLUSTERING_MODEL_PATH",
        "NEM_PREDICTION_MODEL_PATH",
        "NEM_CLASSIFICATION_MODEL_PATH",
        "NEM_PREDICTION_MODEL_PATH_H2",
        "NEM_CLASSIFICATION_MODEL_PATH_H2",
    ):
        monkeypatch.delenv(variable, raising=False)
    assert nem_kmeans.nem_artifact_path().name == "electricity_nem_daily_kmeans.joblib"
    assert nem_model.nem_artifact_path().name == "electricity_nem_daily_demand_rf.joblib"
    assert nem_classifier.nem_artifact_path().name == "electricity_nem_daily_demand_classifier.joblib"
    assert nem_model.nem_h2_artifact_path().name == "electricity_nem_daily_demand_rf_h2.joblib"
    assert nem_classifier.nem_h2_artifact_path().name == "electricity_nem_daily_demand_classifier_h2.joblib"


def test_training_provenance_accepts_runtime_metadata_and_rejects_secret_fields():
    from app.services.model_provenance import ModelProvenanceError, merge_training_model_provenance

    metadata = {
        "model_type": "prediction", "model_name": "RandomForestRegressor",
        "artifact_name": "electricity_nem_daily_demand_rf_h2.joblib", "artifact_format": "joblib",
        "artifact_version": 2, "python_version": platform.python_version(), "sklearn_version": sklearn.__version__,
        "contract_version": 2, "horizon_days": 2,
        "feature_schema_version": "nem_daily_demand_h2_v1",
        "trained_at": "2026-11-25T00:00:00+00:00", "model_parameters": {"n_estimators": 200},
    }
    merged = merge_training_model_provenance(
        _provenance(), metadata, expected_model_type="prediction"
    )
    assert merged["dataset_name"] == NEM_DATASET_NAME
    assert merged["model"] == metadata

    unsafe = {**metadata, "model_parameters": {"service_secret": "do-not-store"}}
    with pytest.raises(ModelProvenanceError, match="sensitive"):
        merge_training_model_provenance(_provenance(), unsafe, expected_model_type="prediction")


def test_clustering_training_provenance_accepts_native_metadata_without_h2_fields():
    from app.services.model_provenance import merge_training_model_provenance

    metadata = {
        "model_type": "clustering", "model_name": "KMeans",
        "artifact_name": "electricity_nem_daily_kmeans.joblib", "artifact_format": "joblib",
        "artifact_version": 1, "contract_version": 1,
        "python_version": platform.python_version(), "sklearn_version": sklearn.__version__,
        "trained_at": "2026-11-25T00:00:00+00:00",
        "model_parameters": {"selected_k": 3, "scaler": "standard"},
    }
    dataset_provenance = {
        "dataset_id": 4, "dataset_name": NEM_DATASET_NAME,
        "dataset_source": NEM_DATASET_SOURCE, "network_code": "NEM",
        "interval": "1d", "metric": "demand", "unit": "MW",
    }

    merged = merge_training_model_provenance(
        dataset_provenance, metadata, expected_model_type="clustering"
    )

    assert merged["model"] == metadata
    assert "horizon_days" not in merged["model"]
    assert "feature_schema_version" not in merged["model"]
