# Backend API

FastAPI backend for Electricity Consumption Analytics. Open Electricity NEM is the active dataset for public electricity, dashboard, analysis and ML workflows: network `NEM`, daily interval `1d`, demand in `MW`, timestamps interpreted in `Australia/Brisbane`. The fixed-horizon Prediction and Classification contract is `nem_daily_demand_h2_v1`. VNM monthly code, data and artifacts remain legacy; they have not been deleted, and active NEM routes do not fall back to them.

## Local setup

From the repository root:

```powershell
Copy-Item .env.example .env
```

Edit `.env`: set a private PostgreSQL password and generate a JWT secret with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the generated value into `JWT_SECRET_KEY`. Do not commit `.env`.

Start the project-owned database service, which uses port `5433` and its own volume:

```powershell
docker compose up -d postgres
```

Install and migrate from `BE`:

```powershell
cd BE
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

The docs are at `http://127.0.0.1:8000/docs`.

## Analysis Service (independent process)

The public Analysis routes remain under `/api/analysis/*` in the Gateway. The Gateway reads validated daily network-level NEM observations from PostgreSQL and calls the private Analysis Service over HTTP. The service reuses the existing analysis functions, validates JSON input, and has no database connection. It exposes `/health` and authenticated internal analysis endpoints; monthly VNM helpers are retained for legacy compatibility and are not the active Gateway data path.

Set these values in the root `.env` before starting either process. Generate a random secret of at least 32 bytes and use the same value for both processes; do not commit the actual secret:

```dotenv
ANALYSIS_SERVICE_URL=http://127.0.0.1:8101
ANALYSIS_SERVICE_SECRET=<private-random-secret-at-least-32-bytes>
ANALYSIS_SERVICE_TIMEOUT_SECONDS=5
```

Run Analysis Service in one terminal from `BE`:

```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn service_apps.analysis.main:app --host 127.0.0.1 --port 8101 --env-file ..\.env
```

Run the Backend API in another terminal from `BE`:

```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --env-file ..\.env
```

Check service health with `Invoke-RestMethod http://127.0.0.1:8101/health`. To check the Gateway path, log in through `/api/auth/login` with a cookie jar, then call `GET http://127.0.0.1:8000/api/analysis/summary` with that cookie. With a valid session and DB, the response should include the analysis summary; stopping Analysis Service should cause the same public route to return `503` with a generic service-unavailable detail. Internal service credentials and URLs are not returned to the browser.

## Clustering Service (independent process)

The Gateway retains public `/api/clustering/*` endpoints, authentication, NEM PostgreSQL reads, and `model_runs` persistence. It calls a separate Clustering Service over HTTP. The service has no database connection and uses daily network-level NEM features. The monthly VNM implementation remains legacy and is not the active Gateway workflow.

Configure a separate random secret of at least 32 bytes in the root `.env`, shared only by the Gateway and Clustering Service:

```dotenv
CLUSTERING_SERVICE_URL=http://127.0.0.1:8102
CLUSTERING_SERVICE_SECRET=<private-random-secret-at-least-32-bytes>
CLUSTERING_SERVICE_TIMEOUT_SECONDS=30
```

Run the Clustering Service in its own terminal from `BE`:

```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn service_apps.clustering.main:app --host 127.0.0.1 --port 8102 --env-file ..\.env
```

Run the Gateway in another terminal from `BE`:

```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --env-file ..\.env
```

Check service health at `http://127.0.0.1:8102/health`. The NEM internal endpoints are `POST /internal/clustering/nem/train` and `POST /internal/clustering/nem/run`; they are not public browser APIs. The Gateway's public train/run routes require an Admin cookie. Train evaluates daily NEM configurations and writes the NEM K-Means artifact; Run loads that artifact and assigns clusters without fitting. Compose configures `NEM_CLUSTERING_MODEL_PATH` with default `/app/artifacts/electricity_nem_daily_kmeans.joblib`. No training runs at service startup.

## Prediction Service (independent process)

The Gateway keeps public `/api/prediction/*` endpoints, user authentication and RBAC, NEM PostgreSQL reads, and `model_runs` persistence. It sends validated daily NEM demand in MW to the separate Prediction Service over HTTP. The service has no database connection; the active model is the NEM H2 implementation, separate from the retained monthly VNM model.

Configure a separate random secret of at least 32 bytes in the root `.env`, shared only by the Gateway and Prediction Service:

```dotenv
PREDICTION_SERVICE_URL=http://127.0.0.1:8103
PREDICTION_SERVICE_SECRET=<private-random-secret-at-least-32-bytes>
PREDICTION_SERVICE_TIMEOUT_SECONDS=120
```

Run the Prediction Service in its own terminal from `BE`:

```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn service_apps.prediction.main:app --host 127.0.0.1 --port 8103 --env-file ..\.env
```

Run the Gateway in another terminal from `BE`:

```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --env-file ..\.env
```

Check health at `http://127.0.0.1:8103/health`. NEM internal endpoints are `POST /internal/prediction/nem/train` and `POST /internal/prediction/nem/run`; they are not public browser APIs. Public Train/Run routes require an Admin cookie. Train fits and saves `electricity_nem_daily_demand_rf_h2.joblib`; Run loads that H2 artifact and predicts without fitting. Compose passes `NEM_PREDICTION_MODEL_PATH_H2`, defaulting to `/app/artifacts/electricity_nem_daily_demand_rf_h2.joblib`. The H2 artifact is distinct from both the NEM H1 and legacy VNM artifacts. No training runs at service startup.

## Classification Service (independent process)

The Gateway retains public `/api/classification/*` endpoints, user authentication and RBAC, NEM PostgreSQL reads, and `model_runs` persistence. It sends validated daily NEM demand in MW to the Classification Service over HTTP. The service has no database connection; the active model classifies H2 demand as binary `Low`/`High`, separate from retained monthly VNM classification code.

Configure a separate random secret of at least 32 bytes in the root `.env`, shared only by the Gateway and Classification Service:

```dotenv
CLASSIFICATION_SERVICE_URL=http://127.0.0.1:8104
CLASSIFICATION_SERVICE_SECRET=<private-random-secret-at-least-32-bytes>
CLASSIFICATION_SERVICE_TIMEOUT_SECONDS=120
```

Run the Classification Service in its own terminal from `BE`:

```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn service_apps.classification.main:app --host 127.0.0.1 --port 8104 --env-file ..\.env
```

Run the Gateway in another terminal from `BE`:

```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --env-file ..\.env
```

Check health at `http://127.0.0.1:8104/health`. NEM internal endpoints are `POST /internal/classification/nem/train` and `POST /internal/classification/nem/run`; they are not public browser APIs. Public Train/Run require an Admin cookie; Analysts can read latest and history. Train fits and writes `electricity_nem_daily_demand_classifier_h2.joblib`, including the training-derived threshold. Run loads that H2 artifact and predicts without fitting. Compose passes `NEM_CLASSIFICATION_MODEL_PATH_H2`, defaulting to `/app/artifacts/electricity_nem_daily_demand_classifier_h2.joblib`. No training runs at service startup.

## First administrator

After starting PostgreSQL and restoring the sanitized handoff database (or applying migrations to a new empty database), create the first Admin with `BE/scripts/create_admin.py`. It reads `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_EMAIL`, and `BOOTSTRAP_ADMIN_PASSWORD` from the process environment, validates them, hashes the password with Argon2, and refuses if any Admin already exists. It does not modify existing users. The script is included in the backend image, so rebuild the image before running it after changing the script.

See [the team setup guide](../docs/TEAM_SETUP.md) for the PowerShell/Docker command. No default account or password is stored in source or `.env.example`.

## Authentication and access

`POST /api/auth/login` accepts JSON `{ "email": "...", "password": "..." }` and sets an expiring HttpOnly JWT cookie. `POST /api/auth/logout` clears that cookie. `GET /api/auth/me` returns the current account. Set `APP_ENV=production` behind HTTPS to enable the cookie's `Secure` attribute. Configure comma-separated browser origins in `CORS_ORIGINS`.

| Access | API groups |
|---|---|
| Public | `GET /api/health`, `GET /api/health/ready`, `POST /api/auth/login`, `POST /api/auth/logout` |
| Authenticated Admin or Analyst | `/api/auth/me`; electricity reads/export; analysis; dashboard; model result/history reads; reports |
| Admin only | user management; legacy dataset upload/import/sync requests (return HTTP 410); clustering train/run; prediction train/run; classification train/run |

All other API routes require the JWT cookie. Role is looked up from PostgreSQL for each request, so disabling an account takes effect on its next request. Browser clients on a different origin must send cookies explicitly (`credentials: "include"` for `fetch`, or `withCredentials: true` for Axios). `CORS_ORIGINS` must list the exact Frontend origin; the API enables credentialed CORS. In production, use HTTPS and `APP_ENV=production` so the auth cookie is Secure. Keep the JWT secret private; it must be a random value of at least 32 bytes.

## Endpoint index

- Health: `GET /api/health`, `GET /api/health/ready`
- Authentication: `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
- Users (Admin): `GET /api/users`, `GET /api/users/{user_id}`, `POST /api/users`, `PATCH /api/users/{user_id}`, `PATCH /api/users/{user_id}/status`
- Dataset metadata/history: `GET /api/datasets`, `GET /api/datasets/{dataset_id}`, `GET /api/datasets/{dataset_id}/history`, `GET /api/datasets/sync/status`. Legacy CSV `POST /api/datasets/upload`, `POST /api/datasets/{dataset_id}/import`, and `POST /api/datasets/sync` remain for compatibility but return HTTP 410 and do not import data.
- Electricity reads: `GET /api/electricity/demand`, `GET /api/electricity/demand/{record_id}`, `GET /api/electricity/demand/statistics`, `GET /api/electricity/demand/export`
- Dashboard: `GET /api/dashboard/overview`
- Analysis: `GET /api/analysis/summary`, `/trend`, `/seasonality`, `/correlation`, `/distribution`, `/scatter`
- Clustering: Admin `POST /api/clustering/train`, `/api/clustering/run`; reads `GET /api/clustering/latest`, `/runs`, `/runs/{run_id}`
- Prediction: Admin `POST /api/prediction/train`, `/run`; reads `GET /api/prediction/latest`, `/runs`, `/runs/{run_id}`
- Classification: Admin `POST /api/classification/train`, `/run`; reads `GET /api/classification/latest`, `/runs`, `/runs/{run_id}`
- Shared model history: `GET /api/model-runs`, `GET /api/model-runs/{run_id}`
- Reports: `GET /api/reports/summary`, `/analysis`, `/model-runs`, `/export`

Demand listing reads Open Electricity NEM observations with `interval` (daily `1d` for the active demand UI), `start_at`, `end_at`, `page`, and `page_size` (maximum 1000). Date filtering uses a half-open range `[start_at, end_at)`; timestamps are displayed in `Australia/Brisbane`. Reports/export currently return CSV for NEM demand observations or NEM ML model-run rows.

## Legacy VNM CSV ingestion (disabled)

The former monthly VNM CSV upload/import/sync workflow is not an active data path. The Gateway returns HTTP 410 for `POST /api/datasets/upload`, `POST /api/datasets/{dataset_id}/import`, and `POST /api/datasets/sync`; it does not report a successful import. Existing VNM Dataset metadata and database rows are retained. The standalone CSV Ingestion Service is opt-in through the `legacy-csv` Compose profile and is not required by the active NEM Gateway workflow. Dataset GET endpoints remain available for metadata and import-history review.

## NEM ML architecture and demo flow

The active flow is **Gateway → internal ML service → Gateway/PostgreSQL**. The Gateway authenticates the user, enforces Admin/Analyst permissions, loads observations through `app/services/nem_ml_data.py`, sends normalized JSON to the service, and writes successful results and provenance to the existing `model_runs.parameters` and `model_runs.metrics` JSONB columns. ML services do not connect to PostgreSQL. No schema migration is required for model-build metadata.

The shared NEM loader resolves the exact Open Electricity dataset name and source, then filters network-level `NEM`, daily (`1d`) observations and verified metric units. It reports data quality and fingerprints; it does not fill missing dates or silently fall back to VNM. Prediction and Classification use daily demand in MW. Clustering uses daily network metrics: Model A has demand, renewable generation and price; Model B adds renewable proportion. `demand_energy` is not a clustering feature.

| Model | Purpose and input | Train/Run behavior |
|---|---|---|
| Clustering | Groups daily NEM observations with similar operating characteristics; cluster labels are not geographic regions. | Train evaluates configurations and writes the NEM K-Means artifact. Run loads that artifact and assigns clusters without fitting. |
| Prediction | Forecasts next-day NEM demand in MW using lag and calendar features. | Train evaluates chronological folds and writes the NEM Random Forest artifact. Run loads it and predicts; it does not retrain. |
| Classification | Predicts next-day daily demand as binary `Low`/`High` in MW. Validation thresholds are computed from each fold's training split. | Train evaluates chronological folds and saves its classifier and threshold. Run loads them and classifies without fitting. |

NEM artifacts are separate from retained VNM legacy artifacts:

| Model | Active artifact | Environment path | Docker Compose default |
|---|---|---|---|
| Clustering | `electricity_nem_daily_kmeans.joblib` | `NEM_CLUSTERING_MODEL_PATH` | `/app/artifacts/electricity_nem_daily_kmeans.joblib` |
| Prediction H2 | `electricity_nem_daily_demand_rf_h2.joblib` | `NEM_PREDICTION_MODEL_PATH_H2` | `/app/artifacts/electricity_nem_daily_demand_rf_h2.joblib` |
| Classification H2 | `electricity_nem_daily_demand_classifier_h2.joblib` | `NEM_CLASSIFICATION_MODEL_PATH_H2` | `/app/artifacts/electricity_nem_daily_demand_classifier_h2.joblib` |

The artifacts are under `BE/artifacts`; Compose mounts that directory into the ML services. Prediction and Classification use H2 contract `nem_daily_demand_h2_v1`: the cutoff is the last complete Brisbane-local date and the target is the next calendar date after the as-of date (two days after cutoff). Train is an explicit Admin action that fits and writes the model artifact; Run loads the saved artifact and performs inference without fitting. The Gateway stores provenance in existing `model_runs` JSONB. Legacy VNM artifacts and separate NEM H1 artifacts are retained but are not substitutes for the H2 artifacts. No API key, password, database URL or service secret is stored in model provenance.

Start the configured services with the root Compose setup described above (`docker compose up -d --build`). For local development, the independent Uvicorn commands in this README's service sections use ports 8102, 8103 and 8104 for Clustering, Prediction and Classification. The public Gateway endpoints retain these routes:

- Admin: `POST /api/clustering/train`, `/api/clustering/run`; likewise `/api/prediction/train`, `/api/prediction/run` and `/api/classification/train`, `/api/classification/run`.
- Analyst or Admin: `GET /api/{model}/latest`, `/api/{model}/runs`, and `/api/{model}/runs/{run_id}` for each model.

Train is an explicit Admin action. Run is also Admin-only and uses the saved artifact. Analysts can read latest/history but cannot Train or Run. The OpenAPI document at `/docs` is the source of truth for request/response details. After login, use the Admin cookie for Train/Run and the Analyst cookie for reads. Compose paths are container paths; local paths must resolve to the same artifact used by the corresponding service.

### Data and evaluation limits

The project data snapshot used during migration was reported to contain about 365 daily observations and about 30 days of five-minute observations; live coverage can change with ingestion and should be checked before a demo. The current ML loader and all three NEM models use daily data, not five-minute rows. Prediction and Classification use chronological validation, but available history is limited and test folds do not guarantee future accuracy. Clustering is unsupervised and its scores describe the evaluated sample/configurations, not future performance. No model accuracy or production readiness is guaranteed by these code paths alone.

Legacy monthly VNM implementations and artifact files (`electricity_demand_kmeans.joblib`, `electricity_demand_rf.joblib`, `electricity_demand_classifier.joblib`) are retained in the repository for compatibility/reference. They are not the active data source for migrated public electricity or NEM ML routes. The active Gateway does not use a VNM fallback.

## Tests

Tests require a separate PostgreSQL database named exactly `electricity_analytics_test`. Do not point `TEST_DATABASE_URL` at the development database: the fixture recreates tables in that isolated test database.

The Compose test database is physically separate from the application database, uses host port `5435`, and has its own named volume. Start it explicitly when needed:

```powershell
docker compose --profile test-db up -d postgres-test
```

The test fixture calls `drop_all()`/`create_all()` and clears test rows. It validates that `TEST_DATABASE_URL` uses PostgreSQL, host `127.0.0.1`/`localhost`, port `5435`, database `electricity_analytics_test`, and user `electricity_test`; it does not fall back to `DATABASE_URL`. Set the URL from a SecureString for the current PowerShell session, using the same password configured as `POSTGRES_TEST_PASSWORD` in the local `.env`:

```powershell
$testPassword = Read-Host "Test database password" -AsSecureString
$plainTestPassword = [System.Net.NetworkCredential]::new("", $testPassword).Password
$escapedTestPassword = [Uri]::EscapeDataString($plainTestPassword)
$env:TEST_DATABASE_URL = "postgresql+psycopg://electricity_test:$escapedTestPassword@127.0.0.1:5435/electricity_analytics_test"
try {
    python -m pytest -p no:cacheprovider -q
}
finally {
    Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
    $plainTestPassword = $null
    $escapedTestPassword = $null
    $testPassword.Dispose()
}
```

Never substitute port `5433` or the application user. This suite is destructive to the isolated test schema only; it must not be pointed at any database with data to preserve. The model integration test sends generated model artifacts to a temporary directory.
