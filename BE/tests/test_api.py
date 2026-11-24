import csv
import io
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import jwt

from app.db.models import Dataset, ElectricityConsumption, ModelRun
from conftest import authenticate
from scripts.import_electricity_data import load_rows


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


def test_analyst_can_read_but_cannot_manage_or_run(client, analyst):
    login_analyst(client, analyst)
    assert client.get("/api/dashboard/overview").status_code == 200
    assert client.get("/api/reports/summary").status_code == 200
    assert client.get("/api/users").status_code == 403
    assert client.get("/api/datasets").status_code == 403
    assert client.post("/api/clustering/run").status_code == 403
    assert client.post("/api/prediction/train").status_code == 403
    assert client.post("/api/classification/run").status_code == 403
    assert client.post("/api/classification/train").status_code == 403
    assert client.post("/api/clustering/train").status_code == 403


def test_upload_validation_import_history_and_idempotency(client, admin):
    login_admin(client, admin)
    invalid = client.post("/api/datasets/upload", data={"name": "bad", "source": "test"}, files={"file": ("bad.csv", b"not,a,valid,schema\n1,2,3,4")})
    assert invalid.status_code == 422
    uploaded = client.post("/api/datasets/upload", data={"name": "test-demand", "source": "fixture"}, files={"file": ("demand.csv", make_csv())})
    assert uploaded.status_code == 201, uploaded.text
    dataset_id = uploaded.json()["id"]
    imported = client.post(f"/api/datasets/{dataset_id}/import")
    assert imported.status_code == 200, imported.text
    assert imported.json()["history"]["inserted_count"] == 1
    repeated = client.post(f"/api/datasets/{dataset_id}/import")
    assert repeated.json()["history"]["skipped_count"] == 1
    assert client.get(f"/api/datasets/{dataset_id}/history").json().__len__() == 2
    assert client.get("/api/datasets").json()["total"] == 1


def test_electricity_pagination_detail_statistics_and_export(client, analyst, db_session):
    dataset = Dataset(name="demand", source="fixture", file_name="demand.csv", record_count=2)
    db_session.add(dataset)
    db_session.flush()
    db_session.add_all([
        ElectricityConsumption(dataset_id=dataset.id, country_id="vnm", country="Vietnam", iso3="VNM", month=date(2026, 8, 1), metric="demand", fuel=None, value=16, unit="TWh"),
        ElectricityConsumption(dataset_id=dataset.id, country_id="vnm", country="Vietnam", iso3="VNM", month=date(2026, 9, 1), metric="demand", fuel=None, value=18, unit="TWh"),
    ])
    db_session.commit()
    login_analyst(client, analyst)
    page = client.get("/api/electricity/demand?page=1&page_size=1").json()
    assert page["total_matches"] == 2 and len(page["records"]) == 1
    assert client.get("/api/electricity/demand?start_month=2026-10&end_month=2026-01").status_code == 422
    assert client.get("/api/electricity/demand/statistics").json()["count"] == 2
    assert client.get(f"/api/electricity/demand/{page['records'][0]['id']}").status_code == 200
    export = client.get("/api/electricity/demand/export")
    assert export.status_code == 200 and "text/csv" in export.headers["content-type"]


def test_dashboard_analysis_model_runs_and_reports(client, analyst, db_session, monkeypatch):
    from app.analysis.correlation import build_correlation
    from app.analysis.distribution import build_distribution
    from app.analysis.seasonality import build_seasonality
    from app.analysis.statistics import build_summary
    from app.analysis.trends import build_trend
    from app.api.routes import analysis as analysis_routes

    def local_analysis(operation, records, **options):
        if operation == "summary":
            return {"unit": "TWh", "start_month": records[0]["month"] if records else None,
                    "end_month": records[-1]["month"] if records else None, **build_summary(records)}
        if operation == "trend":
            return {"unit": "TWh", **build_trend(records, options["window_months"])}
        if operation == "seasonality":
            return {"unit": "TWh", **build_seasonality(records)}
        if operation == "correlation":
            return {"unit": "TWh", **build_correlation(records)}
        return {"unit": "TWh", **build_distribution(records, options["bins"])}

    monkeypatch.setattr(analysis_routes.analysis_service_client, "analyze", local_analysis)
    dataset = Dataset(name="report-dataset", source="fixture", file_name="report.csv", record_count=1)
    db_session.add(dataset)
    db_session.flush()
    db_session.add(ElectricityConsumption(dataset_id=dataset.id, country_id="vnm", country="Vietnam", iso3="VNM", month=date(2026, 9, 1), metric="demand", fuel=None, value=17, unit="TWh"))
    run = ModelRun(model_type="clustering", status="completed", started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), parameters={"k": 2}, metrics={"silhouette_score": 0.7})
    db_session.add(run)
    db_session.commit()
    login_analyst(client, analyst)
    overview = client.get("/api/dashboard/overview").json()
    assert overview["record_count"] == 1 and overview["latest_demand_twh"] == 17
    assert client.get("/api/analysis/summary").json()["count"] == 1
    summary = client.get("/api/analysis/summary").json()
    assert {"unit", "start_month", "end_month", "count", "mean", "median", "min", "max"} == set(summary)
    assert client.get("/api/analysis/trend?window_months=6").json()["window_months"] == 6
    assert client.get("/api/analysis/seasonality").status_code == 200
    assert client.get("/api/analysis/correlation").status_code == 200
    assert client.get("/api/analysis/distribution").status_code == 200
    assert client.get("/api/analysis/summary?start_month=2026-13").status_code == 422
    assert client.get("/api/analysis/trend?window_months=1").status_code == 422
    assert client.get("/api/analysis/distribution?bins=51").status_code == 422
    assert client.get("/api/model-runs?model_type=clustering").json()["total"] == 1
    assert client.get(f"/api/model-runs/{run.id}").json()["parameters"] == {"k": 2}
    assert client.get("/api/clustering/runs").json()["total"] == 1
    assert client.get("/api/reports/analysis").status_code == 200
    assert client.get("/api/reports/model-runs").status_code == 200
    assert "text/csv" in client.get("/api/reports/export?report_type=model-runs").headers["content-type"]


def test_empty_dashboard_and_model_result_lookup(client, analyst):
    login_analyst(client, analyst)
    overview = client.get("/api/dashboard/overview").json()
    assert overview["record_count"] == 0 and overview["latest_demand_twh"] is None
    assert client.get("/api/prediction/latest").status_code == 404
    assert client.get("/api/classification/latest").status_code == 404
    assert client.get("/api/clustering/latest").status_code == 404


def test_sync_status_is_configurable_and_safe(client, admin, monkeypatch):
    login_admin(client, admin)
    monkeypatch.delenv("DATASET_SYNC_URL", raising=False)
    assert client.get("/api/datasets/sync/status").json()["configured"] is False
    assert client.post("/api/datasets/sync").status_code == 503


def test_clustering_prediction_and_classification_real_monthly_dataset(client, admin, db_session, monkeypatch):
    from app.clustering import kmeans as clustering_model
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
    from app.classification import model as classification_model
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
    db_session.commit()
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as artifacts_dir:
        monkeypatch.setattr(clustering_model, "artifact_path", lambda: Path(artifacts_dir) / "clustering_test.joblib")
        monkeypatch.setattr(prediction_model, "_artifact_path", lambda: Path(artifacts_dir) / "prediction_test.joblib")
        monkeypatch.setattr(classification_model, "_artifact_path", lambda: Path(artifacts_dir) / "classification_test.joblib")
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
                f"/internal/clustering/{operation}",
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

        monkeypatch.setattr(
            clustering_routes.clustering_service_client,
            "train",
            lambda records, max_k=5: call_clustering_service(
                "train", {"records": records, "max_k": max_k}
            ),
        )

        def call_prediction_service(operation, records):
            response = prediction_internal_client.post(
                f"/internal/prediction/{operation}",
                json={"records": records},
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
            "train",
            lambda records: call_prediction_service("train", records),
        )
        monkeypatch.setattr(
            prediction_routes.prediction_service_client,
            "run",
            lambda records: call_prediction_service("run", records),
        )

        def call_classification_service(operation, records):
            response = classification_internal_client.post(
                f"/internal/classification/{operation}",
                json={"records": records},
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
            "train",
            lambda records: call_classification_service("train", records),
        )
        monkeypatch.setattr(
            classification_routes.classification_service_client,
            "run",
            lambda records: call_classification_service("run", records),
        )
        monkeypatch.setattr(
            clustering_routes.clustering_service_client,
            "run",
            lambda records: call_clustering_service("run", {"records": records}),
        )
        login_admin(client, admin)

        assert client.post("/api/clustering/run").status_code == 409
        clustering_train = client.post("/api/clustering/train")
        assert clustering_train.status_code == 200, clustering_train.text
        assert clustering_train.json()["metrics"]["stage"] == "training"
        clustering = client.post("/api/clustering/run")
        assert clustering.status_code == 200, clustering.text
        assert clustering.json()["metrics"]["sample_count"] > 0
        assert clustering.json()["metrics"]["stage"] == "run"
        assert client.get("/api/clustering/latest").json()["metrics"]["stage"] == "run"
        assert client.get("/api/clustering/runs").json()["total"] == 3

        prediction_train = client.post("/api/prediction/train")
        assert prediction_train.status_code == 200, prediction_train.text
        assert prediction_train.json()["metrics"]["holdout_sample_count"] > 0
        forecast = client.post("/api/prediction/run")
        assert forecast.status_code == 200, forecast.text
        assert forecast.json()["metrics"]["forecast_month"] == "2026-10"
        assert client.get("/api/prediction/latest").json()["metrics"]["forecast_month"] == "2026-10"
        assert client.get("/api/prediction/runs").json()["total"] == 2

        assert client.post("/api/classification/run").status_code == 409
        classification_train = client.post("/api/classification/train")
        assert classification_train.status_code == 200, classification_train.text
        assert classification_train.json()["metrics"]["holdout_metrics"]["confusion_matrix"]["labels"] == ["low", "medium", "high"]
        classification = client.post("/api/classification/run")
        assert classification.status_code == 200, classification.text
        assert classification.json()["metrics"]["forecast_month"] == "2026-10"
        assert client.get("/api/classification/latest").json()["metrics"]["forecast_month"] == "2026-10"
        assert client.get("/api/classification/runs").json()["total"] == 3


def test_failed_model_attempts_are_recorded_without_fake_results(client, admin, monkeypatch):
    from app.api.routes import clustering as clustering_routes
    from app.clients.clustering import ClusteringServiceRejected
    from app.api.routes import prediction as prediction_routes
    from app.api.routes import classification as classification_routes
    from app.clients.prediction import PredictionServiceRejected
    from app.clients.classification import ClassificationServiceRejected

    def reject_empty_records(*_args, **_kwargs):
        raise ClusteringServiceRejected("At least four months of monthly history are required")

    def reject_prediction_records(*_args, **_kwargs):
        raise PredictionServiceRejected("At least four months of monthly history are required")

    def reject_classification_records(*_args, **_kwargs):
        raise ClassificationServiceRejected("At least four months of monthly history are required")

    monkeypatch.setattr(clustering_routes.clustering_service_client, "train", reject_empty_records)
    monkeypatch.setattr(clustering_routes.clustering_service_client, "run", reject_empty_records)
    monkeypatch.setattr(prediction_routes.prediction_service_client, "train", reject_prediction_records)
    monkeypatch.setattr(prediction_routes.prediction_service_client, "run", reject_prediction_records)
    monkeypatch.setattr(classification_routes.classification_service_client, "train", reject_classification_records)
    monkeypatch.setattr(classification_routes.classification_service_client, "run", reject_classification_records)
    login_admin(client, admin)
    assert client.post("/api/clustering/run").status_code == 422
    assert client.post("/api/prediction/train").status_code == 422
    assert client.post("/api/classification/train").status_code == 422
    runs = client.get("/api/model-runs?status=failed").json()
    assert runs["total"] == 3
    assert {item["model_type"] for item in runs["items"]} == {"clustering", "prediction", "classification"}
