# Backend API

FastAPI backend for monthly Vietnamese electricity demand. The API uses PostgreSQL through the shared SQLAlchemy session dependency; analytics and model routes read `VNM / demand / fuel IS NULL / TWh` rows from `electricity_consumption`.

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

The public Analysis routes remain under `/api/analysis/*` in the Gateway. The Gateway reads the selected monthly records from PostgreSQL and calls the private Analysis Service over HTTP. The service reuses the existing functions in `app/analysis/`, validates JSON input, and has no database connection. It exposes `/health` and authenticated internal `POST /internal/analysis/{summary|trend|seasonality|correlation|distribution}` endpoints.

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

The Gateway retains all public `/api/clustering/*` endpoints, authentication, PostgreSQL reads, and `model_runs` persistence. It calls a separate Clustering Service over HTTP. The Clustering Service has no database connection; it reuses `app/clustering/kmeans.py`, validates monthly records, and authenticates Gateway requests with `X-Clustering-Service-Secret`.

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

Check service health at `http://127.0.0.1:8102/health`. Its internal endpoints are `POST /internal/clustering/train` and `POST /internal/clustering/run`; they are not public browser APIs. The Gateway's public train/run routes remain documented at `http://127.0.0.1:8000/docs` and require an Admin cookie. Train is the only operation that fits or writes the K-Means artifact. Run loads the artifact and returns conflict when it is absent, incompatible, stale, or built from a different monthly dataset. Both processes must resolve the same `CLUSTERING_MODEL_PATH`; if unset in local development, the existing `BE/artifacts/electricity_demand_kmeans.joblib` default is used. No training runs at service startup.

## Prediction Service (independent process)

The Gateway keeps the public `/api/prediction/*` endpoints, user authentication and RBAC, PostgreSQL reads, and `model_runs` persistence. It sends normalized monthly demand records to the separate Prediction Service over HTTP. The service has no database connection and directly reuses `app/prediction/model.py`.

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

Check health at `http://127.0.0.1:8103/health`. Internal endpoints are `POST /internal/prediction/train` and `POST /internal/prediction/run`; they are not public browser APIs. Public train/run routes require an Admin cookie. Train explicitly fits and saves the Random Forest artifact; Run only loads the existing artifact and predicts, and the service does not train at startup. Both processes must resolve the same `PREDICTION_MODEL_PATH` (default `BE/artifacts/electricity_demand_rf.joblib`). Keep that artifact on persistent shared storage when using separate containers.

## First administrator

Create an admin interactively. The password is prompted without echo and is Argon2-hashed; the command only succeeds when there is no active admin yet.

```powershell
cd BE
python .\scripts\create_admin.py --username admin --email admin@example.com
```

There is no default account or password in source code.

## Authentication and access

`POST /api/auth/login` accepts JSON `{ "email": "...", "password": "..." }` and sets an expiring HttpOnly JWT cookie. `POST /api/auth/logout` clears that cookie. `GET /api/auth/me` returns the current account. Set `APP_ENV=production` behind HTTPS to enable the cookie's `Secure` attribute. Configure comma-separated browser origins in `CORS_ORIGINS`.

| Access | API groups |
|---|---|
| Public | `GET /api/health`, `GET /api/health/ready`, `POST /api/auth/login`, `POST /api/auth/logout` |
| Authenticated Admin or Analyst | `/api/auth/me`; electricity reads/export; analysis; dashboard; model result/history reads; reports |
| Admin only | user management; dataset management/upload/import/sync; clustering train/run; prediction train/run; classification train/run |

All other API routes require the JWT cookie. Role is looked up from PostgreSQL for each request, so disabling an account takes effect on its next request. Browser clients on a different origin must send cookies explicitly (`credentials: "include"` for `fetch`, or `withCredentials: true` for Axios). `CORS_ORIGINS` must list the exact Frontend origin; the API enables credentialed CORS. In production, use HTTPS and `APP_ENV=production` so the auth cookie is Secure. Keep the JWT secret private; it must be a random value of at least 32 bytes.

## Endpoint index

- Health: `GET /api/health`, `GET /api/health/ready`
- Authentication: `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
- Users (Admin): `GET /api/users`, `GET /api/users/{user_id}`, `POST /api/users`, `PATCH /api/users/{user_id}`, `PATCH /api/users/{user_id}/status`
- Datasets (Admin): `GET /api/datasets`, `GET /api/datasets/{dataset_id}`, `POST /api/datasets/upload`, `POST /api/datasets/{dataset_id}/import`, `GET /api/datasets/{dataset_id}/history`, `POST /api/datasets/sync`, `GET /api/datasets/sync/status`
- Electricity reads: `GET /api/electricity/demand`, `GET /api/electricity/demand/{record_id}`, `GET /api/electricity/demand/statistics`, `GET /api/electricity/demand/export`
- Dashboard: `GET /api/dashboard/overview`
- Analysis: `GET /api/analysis/summary`, `/trend`, `/seasonality`, `/correlation`, `/distribution`
- Clustering: Admin `POST /api/clustering/train`, `/api/clustering/run`; reads `GET /api/clustering/latest`, `/runs`, `/runs/{run_id}`
- Prediction: Admin `POST /api/prediction/train`, `/run`; reads `GET /api/prediction/latest`, `/runs`, `/runs/{run_id}`
- Classification: Admin `POST /api/classification/train`, `/run`; reads `GET /api/classification/latest`, `/runs`, `/runs/{run_id}`
- Shared model history: `GET /api/model-runs`, `GET /api/model-runs/{run_id}`
- Reports: `GET /api/reports/summary`, `/analysis`, `/model-runs`, `/export`

Demand listing defaults to 100 records per page (`page`, `page_size`, maximum 1000) and supports `start_month` and `end_month` in `YYYY-MM` format. Reports/export currently return CSV for demand or model-run rows.

## Dataset upload and sync

Upload uses multipart form data with `file`, `name`, `source`, and optional `description`:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/datasets/upload `
  -b cookies.txt -F "name=Vietnam demand" -F "source=Ember" `
  -F "file=@..\data\processed\vietnam_electricity_demand.csv"
```

Upload validates CSV columns, monthly dates, numeric values, allowed VNM demand/TWh records, duplicates and the configured size limit. It stores a UUID-named file under ignored `BE/uploads/`. Import is a separate request to `POST /api/datasets/{dataset_id}/import`; PostgreSQL upserts are idempotent and import counts are recorded in `dataset_imports`.

Optional sync accepts an HTTPS `DATASET_SYNC_URL` in `.env`. The URL must return a CSV in the same normalized project format; configure the source outside code, then call `POST /api/datasets/sync`. `GET /api/datasets/sync/status` reports the latest attempt. A failed fetch/validation is recorded and does not delete existing consumption rows. No periodic scheduler is enabled; the service can be called by an external scheduler.

## Model artifacts and demo run order

Training and run are separate operations. For Clustering, Prediction and Classification, `POST /api/{model}/train` fits the model and writes its artifact; `POST /api/{model}/run` only loads that artifact, creates a result in `model_runs`, and does not train. Defaults are `BE/artifacts/electricity_demand_kmeans.joblib`, `electricity_demand_rf.joblib`, and `electricity_demand_classifier.joblib`. Configure `CLUSTERING_MODEL_PATH`, `PREDICTION_MODEL_PATH`, and `CLASSIFICATION_MODEL_PATH` to override them. Persist these files across container recreation when using containers.

Log in first and save the HttpOnly cookie in curl's jar (replace the placeholders locally):

```powershell
curl.exe -i -c admin-cookies.txt -H "Content-Type: application/json" `
  -d '{"email":"<admin-email>","password":"<admin-password>"}' `
  http://127.0.0.1:8000/api/auth/login
```

Build artifacts once before demo (requires Admin and source data loaded):

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/clustering/train -b admin-cookies.txt
curl.exe -X POST http://127.0.0.1:8000/api/prediction/train -b admin-cookies.txt
curl.exe -X POST http://127.0.0.1:8000/api/classification/train -b admin-cookies.txt
```

Reuse the cookie jar with `-b admin-cookies.txt`. Keep the file and credentials out of source control. At demo, call only the three `/run` endpoints. Prediction and Classification require the artifact's `trained_through_month` to equal the latest database month and a complete latest 12-month window. Clustering additionally verifies the exact monthly source-data fingerprint and latest usable feature month. If input data changed, explicitly retrain during preparation; run returns a clear conflict and records a failed attempt rather than fitting implicitly.

To rebuild results after removing only result rows from `model_runs` in a dedicated demo/test database: authenticate as Admin, call `POST /api/clustering/run`, `/api/prediction/run`, and `/api/classification/run`; then authenticate as Analyst and call each `GET /api/{model}/latest` and `/runs`. Keep `electricity_consumption` intact. Analysis endpoints calculate responses from source data at read time and do not have separate persisted pattern rows.

## Tests

Tests require a separate PostgreSQL database named exactly `electricity_analytics_test`. Do not point `TEST_DATABASE_URL` at the development database: the fixture recreates tables in that isolated test database.

Create it once, using the project database container:

```powershell
docker exec electricity-analytics-postgres createdb -U electricity_app -T template0 electricity_analytics_test
```

Set a test-only connection string without changing `.env`, then run tests:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://electricity_app:<same-local-password>@127.0.0.1:5433/electricity_analytics_test"
python -m pytest -p no:cacheprovider -q
```

The model integration test uses the repository's real processed CSV, writes only to the `_test` database, and sends generated model artifacts to a temporary directory.
