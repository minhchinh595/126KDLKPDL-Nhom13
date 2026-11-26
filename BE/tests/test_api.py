import csv
import hashlib
import io
import json
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import jwt

from app.db.models import Dataset, ElectricityConsumption, ModelRun, NEMObservation
from conftest import authenticate
from scripts.import_electricity_data import load_rows
from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE
from app.services import nem_ml_data


def make_csv(value: str = "17.87", month: str = "2026-09") -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["country_id", "country", "iso3", "month", "metric", "fuel", "value", "unit"])
    writer.writerow(["vietnam", "Vietnam", "VNM", month, "demand", "", value, "TWh"])
    return output.getvalue().encode("utf-8")


def login_admin(client, admin):
    authenticate(client, admin.email, "admin-password-test-123")


def login_analyst(client, analyst):
    authenticate(client, analyst.email, "analyst-password-test-123")


def make_nem_clustering_payload(count: int = 120) -> dict:
    import math

    from service_apps.clustering.schemas import NEM_FEATURES

    units = {"demand": "MW", "generation_renewable": "MW", "price": "$/MWh", "renewable_proportion": "%"}
    configurations = {}
    start = date(2026, 1, 1)
    for config_name, feature_names in NEM_FEATURES.items():
        records = []
        for index in range(count):
            phase = index // 30
            values = {
                "demand": 19000 + phase * 1800 + 700 * math.sin(index / 5),
                "generation_renewable": 7200 + (phase % 2) * 1400 + 550 * math.cos(index / 7),
                "price": 45 + phase * 9 + 16 * math.sin(index / 9),
                "renewable_proportion": 38 + phase * 3 + 5 * math.cos(index / 8),
            }
            records.append({"date": (start + timedelta(days=index)).isoformat(), "features": {name: float(values[name]) for name in feature_names}})
        feature_units = {name: units[name] for name in feature_names}
        canonical = {"dataset_id": 4, "dataset_name": NEM_DATASET_NAME, "dataset_source": NEM_DATASET_SOURCE, "network_code": "NEM", "interval": "1d", "feature_names": list(feature_names), "feature_units": feature_units, "records": records}
        configurations[config_name] = {
            "feature_names": list(feature_names), "feature_units": feature_units, "records": records,
            "observation_count": count, "start_date": records[0]["date"], "end_date": records[-1]["date"],
            "dropped_date_count": 0, "dropped_reasons": {},
            "data_fingerprint": hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest(),
            "metric_quality": {name: {"unit": units[name], "iqr_outlier_count": 0} for name in feature_names},
        }
    return {"dataset_id": 4, "dataset_name": NEM_DATASET_NAME, "dataset_source": NEM_DATASET_SOURCE, "network_code": "NEM", "interval": "1d", "configurations": configurations}


def test_health_and_readiness_use_database(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health/ready").json()["database"] == "connected"


def test_auth_cookie_me_logout_and_bad_password(client, admin):
    bad = client.post("/api/auth/login", json={"email": admin.email, "password": "wrong"})
    assert bad.status_code == 401
    response = authenticate(client, admin.email, "admin-password-test-123")
    assert response.json()["role"] == "admin"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "password_hash" not in response.text
    assert client.get("/api/auth/me").json()["email"] == admin.email
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_expired_cookie_and_deactivated_account_are_rejected(client, admin, db_session, monkeypatch):
    from app.core import security

    monkeypatch.setattr(security, "_secret", lambda: "test-only-secret-key-at-least-32-bytes")
    expired = jwt.encode({"sub": str(admin.id), "exp": datetime.now(timezone.utc).timestamp() - 60}, security._secret(), algorithm="HS256")
    client.cookies.set(security.TOKEN_COOKIE, expired)
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.clear()

    authenticate(client, admin.email, "admin-password-test-123")
    admin.is_active = False
    db_session.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_cors_allows_credentialed_frontend_requests(client):
    response = client.options("/api/electricity/demand", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_unauthenticated_routes_reject_requests(client):
    assert client.get("/api/analysis/summary").status_code == 401
    assert client.get("/api/users").status_code == 401
    assert client.get("/api/datasets").status_code == 401
    assert client.post("/api/datasets/sync").status_code == 401
    assert client.post("/api/prediction/train").status_code == 401


def test_admin_user_management_and_last_admin_protection(client, admin):
    login_admin(client, admin)
    response = client.post("/api/users", json={
        "username": "new-analyst", "email": "new@test.local",
        "password": "a-secure-test-password", "role": "analyst",
    })
    assert response.status_code == 201
    user_id = response.json()["id"]
    assert "password_hash" not in response.json()
    assert client.get("/api/users?search=new&role=analyst").json()["total"] == 1
    assert client.patch(f"/api/users/{user_id}/status", json={"is_active": False}).json()["is_active"] is False
    assert client.patch(f"/api/users/{admin.id}", json={"role": "analyst"}).status_code == 409
    duplicate = client.post("/api/users", json={
        "username": "duplicate", "email": "new@test.local",
        "password": "a-secure-test-password", "role": "analyst",
    })
    assert duplicate.status_code == 409
    assert client.patch(f"/api/users/{admin.id}/status", json={"is_active": False}).status_code == 409


def test_analyst_can_read_but_cannot_manage_or_run(client, analyst, db_session):
    dataset = Dataset(name=NEM_DATASET_NAME, source=NEM_DATASET_SOURCE, file_name="API observations", record_count=0)
    db_session.add(dataset)
    db_session.commit()
    login_analyst(client, analyst)
    assert client.get("/api/dashboard/overview").status_code == 200
    assert client.get("/api/reports/summary").status_code == 200
    assert client.get("/api/users").status_code == 403
    assert client.get("/api/datasets").status_code == 200
    assert client.get(f"/api/datasets/{dataset.id}").status_code == 200
    assert client.get(f"/api/datasets/{dataset.id}/history").status_code == 200
    assert client.get("/api/datasets/sync/status").status_code == 200
    assert client.post(
        "/api/datasets/upload",
        data={"name": "analyst-upload", "source": "fixture"},
        files={"file": ("data.csv", make_csv())},
    ).status_code == 403
    assert client.post(f"/api/datasets/{dataset.id}/import").status_code == 403
    assert client.post("/api/datasets/sync").status_code == 403
    assert client.post("/api/clustering/run").status_code == 403
    assert client.post("/api/prediction/train").status_code == 403
    assert client.post("/api/classification/run").status_code == 403
    assert client.post("/api/classification/train").status_code == 403
    assert client.post("/api/clustering/train").status_code == 403


def test_legacy_csv_upload_and_import_are_disabled(client, admin, db_session, monkeypatch):
    from app.api.routes import datasets as dataset_routes

    legacy_dataset = Dataset(
        name="Vietnam demand legacy",
        source="Ember",
        file_name="legacy.csv",
        record_count=93,
        status="imported",
    )
    db_session.add(legacy_dataset)
    db_session.commit()
    login_admin(client, admin)
    calls = []
    monkeypatch.setattr(
        dataset_routes.ingestion_service_client,
        "normalize",
        lambda content: calls.append(len(content)),
    )
    metadata = client.get(f"/api/datasets/{legacy_dataset.id}").json()
    assert metadata["source_role"] == "legacy"
    uploaded = client.post(
        "/api/datasets/upload",
        data={"name": "new-vnm", "source": "Ember"},
        files={"file": ("demand.csv", make_csv())},
    )
    imported = client.post(f"/api/datasets/{legacy_dataset.id}/import")
    assert uploaded.status_code == 410
    assert imported.status_code == 410
    assert "Open Electricity NEM" in uploaded.json()["detail"]
    assert "Open Electricity NEM" in imported.json()["detail"]
    assert client.get(f"/api/datasets/{legacy_dataset.id}").json()["source_role"] == "legacy"
    assert calls == []
    assert client.get(f"/api/datasets/{legacy_dataset.id}/history").json() == []


def test_electricity_pagination_detail_statistics_and_export(client, analyst, db_session):
    dataset = Dataset(name=NEM_DATASET_NAME, source=NEM_DATASET_SOURCE, file_name="API observations", record_count=2)
    db_session.add(dataset)
    db_session.flush()
    db_session.add_all([
        NEMObservation(dataset_id=dataset.id, network_code="NEM", metric="demand", interval="1d", observed_at=datetime(2026, 8, 1, tzinfo=timezone.utc), value=16, unit="MW", result="NEM", grouping_type="network", grouping_code=""),
        NEMObservation(dataset_id=dataset.id, network_code="NEM", metric="demand", interval="1d", observed_at=datetime(2026, 9, 1, tzinfo=timezone.utc), value=18, unit="MW", result="NEM", grouping_type="network", grouping_code=""),
    ])
    db_session.commit()
    login_analyst(client, analyst)
    page = client.get("/api/electricity/demand?page=1&page_size=1").json()
    assert page["total_matches"] == 2 and len(page["records"]) == 1
    assert page["records"][0]["metric"] == "demand" and page["records"][0]["unit"] == "MW"
    assert client.get("/api/electricity/demand?start_at=2026-10-01T00:00:00Z&end_at=2026-01-01T00:00:00Z").status_code == 422
    assert client.get("/api/electricity/demand/statistics").json()["count"] == 2
    assert client.get(f"/api/electricity/demand/{page['records'][0]['id']}").status_code == 200
    export = client.get("/api/electricity/demand/export")
    assert export.status_code == 200 and "text/csv" in export.headers["content-type"]


def test_dashboard_analysis_model_runs_and_reports(client, analyst, db_session, monkeypatch):
    from app.api.routes import analysis as analysis_routes

    def local_analysis(operation, records, **options):
        if operation == "nem-summary": return {"metric": "demand", "interval": "1d", "unit": "MW", "sample_count": len(records), "start_date": "2026-09-01", "end_date": "2026-09-01", "mean": 17, "median": 17, "minimum": 17, "maximum": 17}
        if operation == "nem-trend": return {"metric": "demand", "unit": "MW", "view": options["view"], "aggregation": "test", "records": []}
        if operation == "nem-seasonality": return {"metric": "demand", "unit": "MW", "method": "test", "limitation": "test", "records": []}
        if operation == "nem-correlation": return {"metrics": {}, "alignment": "test", "sample_dates": 1, "matrix": {}, "pair_counts": {}}
        if operation == "nem-distribution": return {"metric": options["metric"], "interval": options["interval"], "unit": "MW", "sample_count": len(records), "bins": []}
        return {"x": {}, "y": {}, "sample_count": 0, "points": []}

    monkeypatch.setattr(analysis_routes.analysis_service_client, "analyze", local_analysis)
    dataset = Dataset(name=NEM_DATASET_NAME, source=NEM_DATASET_SOURCE, file_name="API observations", record_count=5)
    db_session.add(dataset)
    db_session.flush()
    db_session.add_all([
        NEMObservation(dataset_id=dataset.id, network_code="NEM", metric="demand", interval="1d", observed_at=datetime(2026, 9, 1, tzinfo=timezone.utc), value=17, unit="MW", result="NEM", grouping_type="network", grouping_code=""),
        NEMObservation(dataset_id=dataset.id, network_code="NEM", metric="price", interval="1d", observed_at=datetime(2026, 9, 1, tzinfo=timezone.utc), value=-5, unit="$/MWh", result="NEM", grouping_type="network", grouping_code=""),
        NEMObservation(dataset_id=dataset.id, network_code="NEM", metric="demand_energy", interval="1d", observed_at=datetime(2026, 9, 1, tzinfo=timezone.utc), value=400, unit="MWh", result="NEM", grouping_type="network", grouping_code=""),
        NEMObservation(dataset_id=dataset.id, network_code="NEM", metric="generation_renewable", interval="1d", observed_at=datetime(2026, 9, 1, tzinfo=timezone.utc), value=8, unit="MW", result="NEM", grouping_type="network", grouping_code=""),
        NEMObservation(dataset_id=dataset.id, network_code="NEM", metric="renewable_proportion", interval="1d", observed_at=datetime(2026, 9, 1, tzinfo=timezone.utc), value=47, unit="%", result="NEM", grouping_type="network", grouping_code=""),
    ])
    run = ModelRun(
        model_type="clustering", status="completed",
        started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
        parameters={"k": 2, "provenance": {
            "dataset_name": NEM_DATASET_NAME, "dataset_source": NEM_DATASET_SOURCE,
            "network_code": "NEM", "interval": "1d",
        }},
        metrics={"silhouette_score": 0.7},
    )
    db_session.add(run)
    db_session.commit()
    login_analyst(client, analyst)
    overview = client.get("/api/dashboard/overview").json()
    assert overview["total_observations"] == 5 and overview["latest_daily_demand_mw"] == 17
    assert client.get("/api/analysis/summary").json()["sample_count"] == 5
    summary = client.get("/api/analysis/summary").json()
    assert summary["metric"] == "demand" and summary["unit"] == "MW" and summary["sample_count"] == 5
    assert client.get("/api/analysis/trend?view=month").json()["view"] == "month"
    assert client.get("/api/analysis/seasonality").status_code == 200
    assert client.get("/api/analysis/correlation").status_code == 200
    assert client.get("/api/analysis/distribution").status_code == 200
    assert client.get("/api/analysis/summary?start_at=2026-09-01T00:00:00Z&end_at=2026-08-01T00:00:00Z").status_code == 422
    assert client.get("/api/analysis/trend?view=year").status_code == 422
    assert client.get("/api/analysis/distribution?bins=51").status_code == 422
    assert client.get("/api/model-runs?model_type=clustering").json()["total"] == 1
    run_parameters = client.get(f"/api/model-runs/{run.id}").json()["parameters"]
    assert run_parameters["k"] == 2
    assert run_parameters["provenance"] == {
        "dataset_name": NEM_DATASET_NAME,
        "dataset_source": NEM_DATASET_SOURCE,
        "network_code": "NEM",
        "interval": "1d",
    }
    assert client.get("/api/clustering/runs").json()["total"] == 1
    assert client.get("/api/reports/analysis").status_code == 200
    assert client.get("/api/reports/model-runs").status_code == 200
    assert "text/csv" in client.get("/api/reports/export?report_type=model-runs").headers["content-type"]


def test_empty_dashboard_and_model_result_lookup(client, analyst, db_session):
    db_session.add(Dataset(name=NEM_DATASET_NAME, source=NEM_DATASET_SOURCE, file_name="API observations", record_count=0, status="ready"))
    db_session.commit()
    login_analyst(client, analyst)
    overview = client.get("/api/dashboard/overview").json()
    assert overview["total_observations"] == 0 and overview["latest_daily_demand_mw"] is None
    assert client.get("/api/prediction/latest").status_code == 404
    assert client.get("/api/classification/latest").status_code == 404
    assert client.get("/api/clustering/latest").status_code == 404


def test_sync_status_is_configurable_and_safe(client, admin, monkeypatch):
    login_admin(client, admin)
    monkeypatch.setenv("DATASET_SYNC_URL", "https://example.invalid/vnm.csv")
    assert client.get("/api/datasets/sync/status").json()["configured"] is False
    assert client.post("/api/datasets/sync").status_code == 410


def test_dataset_sync_is_disabled_without_fetch_or_ingestion(client, admin, monkeypatch):
    from app.api.routes import datasets as dataset_routes

    calls = []

    def unexpected(*_args, **_kwargs):
        raise AssertionError("disabled sync must not fetch or normalize CSV")

    monkeypatch.setattr(dataset_routes, "urlopen", unexpected, raising=False)
    monkeypatch.setenv("DATASET_SYNC_URL", "https://data.example.test/monthly.csv")
    monkeypatch.setattr(
        dataset_routes.ingestion_service_client,
        "normalize",
        lambda content: calls.append(len(content)),
    )
    login_admin(client, admin)

    response = client.post("/api/datasets/sync")
    assert response.status_code == 410
    assert "Open Electricity NEM" in response.json()["detail"]
    assert calls == []


def test_clustering_prediction_and_classification_real_monthly_dataset(client, admin, db_session, monkeypatch):
    from app.clustering import kmeans as clustering_model
    from app.clustering import nem_kmeans
    from app.api.routes import clustering as clustering_routes
    from app.api.routes import prediction as prediction_routes
    from app.api.routes import classification as classification_routes
    from app.clients.prediction import (
        PredictionServiceConflict,
        PredictionServiceRejected,
        PredictionServiceUnavailable,
    )
    from app.clients.classification import (
        ClassificationArtifactWriteError,
        ClassificationServiceConflict,
        ClassificationServiceError,
        ClassificationServiceRejected,
        ClassificationServiceUnavailable,
    )
    from app.clients.clustering import (
        ClusteringServiceConflict,
        ClusteringServiceRejected,
        ClusteringServiceUnavailable,
    )
    from app.prediction import model as prediction_model
    from app.prediction import nem_model as nem_prediction_model
    from app.classification import model as classification_model
    from app.classification import nem_classifier as nem_classification_model
    from fastapi.testclient import TestClient as ServiceTestClient
    from service_apps.clustering.main import app as clustering_service_app
    from service_apps.prediction.main import app as prediction_service_app
    from service_apps.classification.main import app as classification_service_app

    root = Path(__file__).resolve().parents[2]
    csv_path = root / "data" / "processed" / "vietnam_electricity_demand.csv"
    rows = load_rows(csv_path)
    dataset = Dataset(name="real-model-fixture", source="Ember test fixture", file_name=csv_path.name, record_count=len(rows), status="imported")
    db_session.add(dataset)
    db_session.flush()
    db_session.add_all([ElectricityConsumption(dataset_id=dataset.id, **row) for row in rows])
    nem_dataset = Dataset(
        name=NEM_DATASET_NAME,
        source=NEM_DATASET_SOURCE,
        file_name="Open Electricity API observations",
        description="NEM daily demand integration fixture",
        record_count=365,
        status="ready",
    )
    db_session.add(nem_dataset)
    db_session.flush()
    nem_end = date(2026, 11, 25)
    nem_start = nem_end - timedelta(days=364)
    nem_offset = timezone(timedelta(hours=10))
    db_session.add_all([
        NEMObservation(
            dataset_id=nem_dataset.id,
            network_code="NEM",
            metric="demand",
            interval="1d",
            observed_at=datetime.combine(nem_start + timedelta(days=index), datetime.min.time(), tzinfo=nem_offset),
            value=15000 + index * 5 + (index % 7) * 120,
            unit="MW",
            result="Demand",
            grouping_type="network",
            grouping_code="",
        )
        for index in range(365)
    ])
    db_session.commit()
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as artifacts_dir:
        monkeypatch.setattr(clustering_model, "artifact_path", lambda: Path(artifacts_dir) / "clustering_test.joblib")
        monkeypatch.setattr(nem_kmeans, "nem_artifact_path", lambda: Path(artifacts_dir) / "electricity_nem_daily_kmeans.joblib")
        monkeypatch.setattr(prediction_model, "_artifact_path", lambda: Path(artifacts_dir) / "prediction_test.joblib")
        monkeypatch.setattr(nem_prediction_model, "nem_h2_artifact_path", lambda: Path(artifacts_dir) / "electricity_nem_daily_demand_rf_h2.joblib")
        monkeypatch.setattr(nem_prediction_model, "nem_artifact_path", lambda: Path(artifacts_dir) / "electricity_nem_daily_demand_rf.joblib")
        monkeypatch.setattr(classification_model, "_artifact_path", lambda: Path(artifacts_dir) / "classification_test.joblib")
        monkeypatch.setattr(nem_classification_model, "nem_h2_artifact_path", lambda: Path(artifacts_dir) / "electricity_nem_daily_demand_classifier_h2.joblib")
        monkeypatch.setattr(nem_classification_model, "nem_artifact_path", lambda: Path(artifacts_dir) / "electricity_nem_daily_demand_classifier.joblib")
        fixed_nem_forecast_dates = lambda _now=None: (
            date(2026, 11, 26),
            date(2026, 11, 25),
            date(2026, 11, 27),
        )
        monkeypatch.setattr(nem_ml_data, "nem_forecast_dates", fixed_nem_forecast_dates)
        monkeypatch.setattr(prediction_routes, "nem_forecast_dates", fixed_nem_forecast_dates)
        monkeypatch.setattr(classification_routes, "nem_forecast_dates", fixed_nem_forecast_dates)
        secret = "clustering-integration-test-secret-at-least-32-bytes"
        monkeypatch.setenv("CLUSTERING_SERVICE_SECRET", secret)
        service_client = ServiceTestClient(clustering_service_app)
        prediction_secret = "prediction-integration-test-secret-at-least-32-bytes"
        monkeypatch.setenv("PREDICTION_SERVICE_SECRET", prediction_secret)
        prediction_internal_client = ServiceTestClient(prediction_service_app)
        classification_secret = "classification-integration-test-secret-at-least-32-bytes"
        monkeypatch.setenv("CLASSIFICATION_SERVICE_SECRET", classification_secret)
        classification_internal_client = ServiceTestClient(classification_service_app)

        def call_clustering_service(operation, payload):
            response = service_client.post(
                f"/internal/clustering/nem/{operation}",
                json=payload,
                headers={"X-Clustering-Service-Secret": secret},
            )
            if response.status_code == 409:
                raise ClusteringServiceConflict(response.json()["detail"])
            if response.status_code == 422:
                raise ClusteringServiceRejected(response.json()["detail"])
            if response.status_code >= 500:
                raise ClusteringServiceUnavailable("Clustering Service is unavailable")
            assert response.status_code == 200, response.text
            return response.json()

        nem_payload = make_nem_clustering_payload()
        monkeypatch.setattr(clustering_routes, "_load_nem_clustering_payload", lambda _db: nem_payload)
        monkeypatch.setattr(
            clustering_routes.clustering_service_client,
            "train_nem",
            lambda payload, max_k=5: call_clustering_service(
                "train", {**payload, "max_k": max_k}
            ),
        )

        def call_prediction_service(operation, payload):
            response = prediction_internal_client.post(
                f"/internal/prediction/nem/{operation}",
                json=payload,
                headers={"X-Prediction-Service-Secret": prediction_secret},
            )
            if response.status_code == 409:
                raise PredictionServiceConflict(response.json()["detail"])
            if response.status_code == 422:
                raise PredictionServiceRejected(response.json()["detail"])
            if response.status_code >= 500:
                raise PredictionServiceUnavailable("Prediction Service is unavailable")
            assert response.status_code == 200, response.text
            return response.json()

        monkeypatch.setattr(
            prediction_routes.prediction_service_client,
            "train_nem",
            lambda payload: call_prediction_service("train", payload),
        )
        monkeypatch.setattr(
            prediction_routes.prediction_service_client,
            "run_nem",
            lambda payload: call_prediction_service("run", payload),
        )

        def call_classification_service(operation, payload):
            response = classification_internal_client.post(
                f"/internal/classification/nem/{operation}",
                json=payload,
                headers={"X-Classification-Service-Secret": classification_secret},
            )
            if response.status_code == 409:
                raise ClassificationServiceConflict(response.json()["detail"])
            if response.status_code == 422:
                raise ClassificationServiceRejected(response.json()["detail"])
            if response.status_code == 507:
                raise ClassificationArtifactWriteError(response.json()["detail"])
            if response.status_code == 500:
                raise ClassificationServiceError("Classification Service failed")
            if response.status_code >= 500:
                raise ClassificationServiceUnavailable("Classification Service is unavailable")
            assert response.status_code == 200, response.text
            return response.json()

        monkeypatch.setattr(
            classification_routes.classification_service_client,
            "train_nem",
            lambda payload: call_classification_service("train", payload),
        )
        monkeypatch.setattr(
            classification_routes.classification_service_client,
            "run_nem",
            lambda payload: call_classification_service("run", payload),
        )
        monkeypatch.setattr(
            clustering_routes.clustering_service_client,
            "run_nem",
            lambda payload: call_clustering_service("run", payload),
        )
        login_admin(client, admin)

        assert client.post("/api/clustering/run").status_code == 409
        clustering_train = client.post("/api/clustering/train")
        assert clustering_train.status_code == 200, clustering_train.text
        assert clustering_train.json()["metrics"]["stage"] == "training"
        clustering = client.post("/api/clustering/run")
        assert clustering.status_code == 200, clustering.text
        assert clustering.json()["metrics"]["run_observation_count"] > 0
        assert clustering.json()["metrics"]["stage"] == "run"
        assert client.get("/api/clustering/latest").json()["metrics"]["stage"] == "run"
        assert client.get("/api/clustering/runs").json()["total"] == 3

        prediction_train = client.post("/api/prediction/train")
        assert prediction_train.status_code == 200, prediction_train.text
        assert prediction_train.json()["metrics"]["training_sample_count"] > 0
        forecast = client.post("/api/prediction/run")
        assert forecast.status_code == 200, forecast.text
        assert forecast.json()["metrics"]["forecast_date"] == "2026-11-27"
        assert forecast.json()["metrics"]["cutoff_date"] == "2026-11-25"
        assert forecast.json()["metrics"]["unit"] == "MW"
        assert client.get("/api/prediction/latest").json()["metrics"]["forecast_date"] == "2026-11-27"
        assert client.get("/api/prediction/runs").json()["total"] == 2

        assert client.post("/api/classification/run").status_code == 409
        classification_train = client.post("/api/classification/train")
        assert classification_train.status_code == 200, classification_train.text
        classification_training_metrics = classification_train.json()["metrics"]
        assert classification_training_metrics["labels"] == ["Low", "High"]
        assert classification_training_metrics["target"] == "daily_demand_level"
        assert classification_training_metrics["unit"] == "MW"
        validation = classification_training_metrics["validation"]
        assert validation["strategy"] == "TimeSeriesSplit chronological rolling-origin"
        assert validation["shuffle"] is False
        assert validation["fold_count"] == 4
        assert len(validation["folds"]) == validation["fold_count"]
        for fold in validation["folds"]:
            assert fold["training_period"]["end"] < fold["validation_period"]["start"]
            for metric_set in (fold["random_forest"], fold["majority_class_baseline"]):
                assert metric_set["confusion_matrix"]["labels"] == ["Low", "High"]
                matrix = metric_set["confusion_matrix"]["matrix"]
                assert len(matrix) == 2 and all(len(row) == 2 for row in matrix)
                assert all(isinstance(value, int) and value >= 0 for row in matrix for value in row)
                assert {"accuracy", "precision_high", "recall_high", "macro_f1"} <= metric_set.keys()
        assert "pooled_validation_metrics" in validation
        classification = client.post("/api/classification/run")
        assert classification.status_code == 200, classification.text
        assert classification.json()["metrics"]["forecast_date"] == "2026-11-27"
        assert classification.json()["metrics"]["cutoff_date"] == "2026-11-25"
        assert classification.json()["metrics"]["unit"] == "MW"
        assert classification.json()["metrics"]["predicted_level"] in {"Low", "High"}
        assert client.get("/api/classification/latest").json()["metrics"]["forecast_date"] == "2026-11-27"
        assert client.get("/api/classification/runs").json()["total"] == 3


def test_failed_model_attempts_are_recorded_without_fake_results(client, admin, db_session, monkeypatch):
    from app.api.routes import clustering as clustering_routes
    from app.clients.clustering import ClusteringServiceRejected
    from app.api.routes import prediction as prediction_routes
    from app.api.routes import classification as classification_routes
    from app.clients.prediction import PredictionServiceRejected
    from app.clients.classification import ClassificationServiceRejected
    from decimal import Decimal
    from app.services.nem_ml_data import (
        DailyObservation,
        NEMDailyMLData,
        _fingerprint,
        build_nem_prediction_payload,
    )

    daily_end = date(2026, 11, 25)
    daily_start = daily_end - timedelta(days=39)
    brisbane = timezone(timedelta(hours=10))
    observations = tuple(
        DailyObservation(
            datetime.combine(daily_start + timedelta(days=index), datetime.min.time(), tzinfo=brisbane),
            Decimal(str(15000 + index * 10)),
            "MW",
            "Demand",
        )
        for index in range(40)
    )
    daily_fingerprint = _fingerprint(
        dataset_id=83,
        dataset_name=NEM_DATASET_NAME,
        dataset_source=NEM_DATASET_SOURCE,
        network_code="NEM",
        metric="demand",
        interval="1d",
        unit="MW",
        rows=observations,
    )
    daily_data = NEMDailyMLData(
        dataset_id=83,
        dataset_name=NEM_DATASET_NAME,
        dataset_source=NEM_DATASET_SOURCE,
        network_code="NEM",
        metric="demand",
        interval="1d",
        unit="MW",
        observations=observations,
        start_date=daily_start,
        end_date=daily_end,
        missing_dates=(),
        duplicate_timestamps=(),
        duplicate_local_dates=(),
        unit_mismatch_count=0,
        null_timestamp_count=0,
        timezone_naive_count=0,
        null_value_count=0,
        invalid_value_count=0,
        non_finite_value_count=0,
        zero_count=0,
        negative_count=0,
        data_fingerprint=daily_fingerprint,
    )
    nem_daily_payload = build_nem_prediction_payload(daily_data)
    clustering_payload = make_nem_clustering_payload()
    assert clustering_routes._nem_provenance(clustering_payload)["network_code"] == "NEM"
    assert prediction_routes._nem_provenance(nem_daily_payload)["network_code"] == "NEM"
    assert classification_routes._nem_provenance(nem_daily_payload)["network_code"] == "NEM"

    rejection_calls = []

    def reject_empty_records(*_args, **_kwargs):
        rejection_calls.append("clustering")
        raise ClusteringServiceRejected("At least four months of monthly history are required")

    def reject_prediction_records(*_args, **_kwargs):
        rejection_calls.append("prediction")
        raise PredictionServiceRejected("At least four months of monthly history are required")

    def reject_classification_records(*_args, **_kwargs):
        rejection_calls.append("classification")
        raise ClassificationServiceRejected("At least four months of monthly history are required")

    monkeypatch.setattr(
        clustering_routes,
        "_load_nem_clustering_payload",
        lambda _db: clustering_payload,
    )
    monkeypatch.setattr(clustering_routes.clustering_service_client, "train_nem", reject_empty_records)
    monkeypatch.setattr(clustering_routes.clustering_service_client, "run_nem", reject_empty_records)
    monkeypatch.setattr(prediction_routes, "_load_nem_prediction_payload", lambda _db: nem_daily_payload)
    monkeypatch.setattr(prediction_routes.prediction_service_client, "train_nem", reject_prediction_records)
    monkeypatch.setattr(prediction_routes.prediction_service_client, "run_nem", reject_prediction_records)
    monkeypatch.setattr(classification_routes, "_load_nem_classification_payload", lambda _db: nem_daily_payload)
    monkeypatch.setattr(classification_routes.classification_service_client, "train_nem", reject_classification_records)
    monkeypatch.setattr(classification_routes.classification_service_client, "run_nem", reject_classification_records)
    login_admin(client, admin)
    assert client.post("/api/clustering/run").status_code == 422
    assert client.post("/api/prediction/train").status_code == 422
    assert client.post("/api/classification/train").status_code == 422
    assert rejection_calls == ["clustering", "prediction", "classification"]
    failed_runs = db_session.query(ModelRun).filter(ModelRun.status == "failed").all()
    assert len(failed_runs) == 3
    assert {run.model_type for run in failed_runs} == {"clustering", "prediction", "classification"}
    assert all(run.metrics is None for run in failed_runs)
