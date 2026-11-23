import tempfile
from pathlib import Path

from app.main import app
from app.services.electricity import DEFAULT_DATA_PATH, load_demand


def test_processed_dataset_matches_raw_source():
    processed = load_demand(DEFAULT_DATA_PATH)
    raw = load_demand(DEFAULT_DATA_PATH.parents[1] / "raw" / "ember-monthly-generation.csv")
    assert processed["records"] == raw["records"]
    assert processed["total"] == 93


def test_loader_sorts_filters_and_preserves_zero():
    with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
        path = Path(directory) / "demand.csv"
        path.write_text(
            "iso3,month,metric,fuel,value,unit\nVNM,2025-02,demand,,2,TWh\nARG,2025-01,demand,,99,TWh\nVNM,2025-01,demand,,0,TWh\n",
            encoding="utf-8",
        )
        data = load_demand(path)
        assert data["total"] == 2
        assert data["records"] == [{"month": "2025-01", "value": 0.0}, {"month": "2025-02", "value": 2.0}]


def test_loader_rejects_duplicate_or_invalid_records():
    with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
        path = Path(directory) / "bad.csv"
        path.write_text(
            "iso3,month,metric,fuel,value,unit\nVNM,2025-01,demand,,1,TWh\nVNM,2025-01,demand,,2,TWh\n",
            encoding="utf-8",
        )
        try:
            load_demand(path)
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate month was accepted")


def test_openapi_contains_preserved_and_added_routes():
    schema = app.openapi()
    paths = schema["paths"]
    expected = {
        "/api/electricity/demand", "/api/analysis/summary", "/api/analysis/trend",
        "/api/analysis/seasonality", "/api/analysis/correlation", "/api/analysis/distribution",
        "/api/clustering/run", "/api/prediction/run", "/api/classification/run",
        "/api/auth/login", "/api/users", "/api/datasets/upload", "/api/dashboard/overview",
        "/api/model-runs", "/api/reports/export",
    }
    assert expected <= paths.keys()
    assert "JWT HttpOnly cookie" in schema["components"]["securitySchemes"]
