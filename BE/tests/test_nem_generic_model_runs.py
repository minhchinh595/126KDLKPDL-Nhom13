import csv
from datetime import datetime, timezone
from io import StringIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.api.routes import model_runs, reports
from app.db.models import ModelRun
from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE


MODEL_TYPES = ("clustering", "prediction", "classification")


def _provenance(
    *, dataset_name=NEM_DATASET_NAME, dataset_source=NEM_DATASET_SOURCE,
    network_code="NEM", interval="1d", metric="demand", unit="MW",
    dataset_id=4, horizon_days=2, feature_schema_version="nem_daily_demand_h2_v1",
):
    return {
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "dataset_source": dataset_source,
        "network_code": network_code,
        "interval": interval,
        "metric": metric,
        "unit": unit,
        "horizon_days": horizon_days,
        "feature_schema_version": feature_schema_version,
    }


def _run(run_id, model_type, provenance, *, status="completed"):
    return ModelRun(
        id=run_id,
        model_type=model_type,
        status=status,
        created_at=datetime(2026, 11, 25, 0, run_id % 60, tzinfo=timezone.utc),
        started_at=None,
        completed_at=None,
        parameters={"provenance": provenance} if provenance is not None else {"legacy": True},
        metrics={
            "marker": f"run-{run_id}",
            **(
                {
                    "stage": "forecast",
                    "artifact_name": (
                        "electricity_nem_daily_demand_rf_h2.joblib"
                        if model_type == "prediction"
                        else "electricity_nem_daily_demand_classifier_h2.joblib"
                    ),
                }
                if model_type in {"prediction", "classification"}
                else {}
            ),
        },
        error_message=None,
    )


class FakeModelRunSession:
    """Fake query session that checks the SQL identity predicate and returns fixtures."""

    def __init__(self, rows, *, requested_model_type=None, requested_status=None, requested_id=None):
        self.rows = rows
        self.requested_model_type = requested_model_type
        self.requested_status = requested_status
        self.requested_id = requested_id

    def _matching(self, statement):
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)
        params = compiled.params
        assert NEM_DATASET_NAME in params.values()
        assert NEM_DATASET_SOURCE in params.values()
        assert "NEM" in params.values()
        assert "1d" in params.values()
        assert "dataset_name" in params.values()
        assert "dataset_source" in params.values()
        assert "network_code" in params.values()
        assert "interval" in params.values()
        if "horizon_days" in sql:
            assert "feature_schema_version" in params.values()
            assert "electricity_nem_daily_demand_rf_h2.joblib" in params.values() or "electricity_nem_daily_demand_classifier_h2.joblib" in params.values()

        rows = []
        for row in self.rows:
            provenance = (row.parameters or {}).get("provenance") or {}
            matches = (
                row.model_type in MODEL_TYPES
                and provenance.get("dataset_name") == NEM_DATASET_NAME
                and provenance.get("dataset_source") == NEM_DATASET_SOURCE
                and provenance.get("network_code") == "NEM"
                and provenance.get("interval") == "1d"
            )
            if row.model_type in {"prediction", "classification"}:
                matches = matches and provenance.get("metric") == "demand" and provenance.get("unit") == "MW"
                expected_artifact = (
                    "electricity_nem_daily_demand_rf_h2.joblib"
                    if row.model_type == "prediction"
                    else "electricity_nem_daily_demand_classifier_h2.joblib"
                )
                matches = matches and (
                    provenance.get("horizon_days") == 2
                    and provenance.get("feature_schema_version") == "nem_daily_demand_h2_v1"
                    and isinstance(provenance.get("dataset_id"), int)
                    and provenance.get("dataset_id") > 0
                    and (row.status != "completed" or row.metrics.get("artifact_name") == expected_artifact)
                )
            if self.requested_model_type is not None:
                assert self.requested_model_type in params.values()
                assert "model_runs.model_type =" in sql
                matches = matches and row.model_type == self.requested_model_type
            if self.requested_status is not None:
                assert self.requested_status in params.values()
                matches = matches and row.status == self.requested_status
            if self.requested_id is not None:
                assert self.requested_id in params.values()
                matches = matches and row.id == self.requested_id
            if matches:
                rows.append(row)

        order = "asc" if "model_runs.created_at ASC" in sql else "desc"
        rows.sort(key=lambda row: (row.created_at, row.id), reverse=order == "desc")
        offset = getattr(statement._offset, "value", statement._offset) or 0
        limit = getattr(statement._limit, "value", statement._limit)
        rows = rows[offset:]
        return rows if limit is None else rows[:limit]

    def scalars(self, statement):
        return FakeScalarResult(self._matching(statement))

    def scalar(self, statement):
        return len(self._matching(statement))

    def execute(self, statement):
        rows = self._matching(statement)
        return SimpleNamespace(scalar_one_or_none=lambda: rows[0] if rows else None)


class FakeScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)


def _rows():
    return [
        _run(1, "clustering", _provenance()),
        _run(2, "prediction", _provenance()),
        _run(3, "classification", _provenance()),
        _run(4, "clustering", _provenance(dataset_name="Legacy VNM")),
        _run(5, "prediction", None),
        _run(6, "classification", _provenance(dataset_source="https://example.invalid/other")),
        _run(7, "prediction", _provenance(network_code="NSW1")),
        _run(8, "classification", _provenance(interval="5m")),
        _run(9, "prediction", _provenance(metric="price")),
        _run(10, "classification", _provenance(unit="TWh")),
        _run(11, "clustering", _provenance(), status="failed"),
        _run(12, "prediction", _provenance(horizon_days=1)),
        _run(13, "classification", _provenance(feature_schema_version="nem_daily_demand_h1_v1")),
        _run(14, "prediction", _provenance(dataset_id=0)),
    ]


def test_reports_model_runs_returns_only_nem_h2_ml_runs_and_honors_type_filter():
    all_runs = reports.report_model_runs(db=FakeModelRunSession(_rows()))
    assert {run.id for run in all_runs["items"]} == {1, 2, 3, 11}
    assert all_runs["limit"] == 500

    predictions = reports.report_model_runs(
        model_type="prediction", db=FakeModelRunSession(_rows(), requested_model_type="prediction")
    )
    assert [run.id for run in predictions["items"]] == [2]


def test_generic_model_runs_filters_before_count_and_pagination():
    db = FakeModelRunSession(_rows(), requested_model_type="prediction", requested_status="completed")
    result = model_runs.list_model_runs(
        model_type="prediction", run_status="completed", order="desc", page=1, page_size=20, db=db
    )
    assert [run.id for run in result["items"]] == [2]
    assert result["total"] == 1
    assert result["pages"] == 1


def test_generic_model_run_detail_hides_legacy_and_invalid_provenance():
    db = FakeModelRunSession(_rows(), requested_id=2)
    assert model_runs.get_model_run(2, db=db).id == 2

    with pytest.raises(HTTPException) as error:
        model_runs.get_model_run(4, db=FakeModelRunSession(_rows(), requested_id=4))
    assert error.value.status_code == 404

    for invalid_h2_id in (12, 13, 14):
        with pytest.raises(HTTPException) as h2_error:
            model_runs.get_model_run(invalid_h2_id, db=FakeModelRunSession(_rows(), requested_id=invalid_h2_id))
        assert h2_error.value.status_code == 404


def test_reports_model_run_export_contains_only_nem_ml_runs():
    response = reports.export_report(report_type="model-runs", db=FakeModelRunSession(_rows()))
    rows = list(csv.reader(StringIO(response.body.decode("utf-8"))))
    exported_ids = {int(row[0]) for row in rows[1:]}
    assert exported_ids == {1, 2, 3, 11}
    assert "model_runs_report.csv" in response.headers["content-disposition"]


def test_empty_nem_model_run_results_keep_existing_response_shapes():
    db = FakeModelRunSession([_run(20, "clustering", None)])
    report_result = reports.report_model_runs(db=db)
    assert report_result == {"items": [], "limit": 500}

    list_result = model_runs.list_model_runs(page=1, page_size=20, db=db)
    assert list_result == {"items": [], "page": 1, "page_size": 20, "total": 0, "pages": 0}

    response = reports.export_report(report_type="model-runs", db=db)
    rows = list(csv.reader(StringIO(response.body.decode("utf-8"))))
    assert len(rows) == 1
