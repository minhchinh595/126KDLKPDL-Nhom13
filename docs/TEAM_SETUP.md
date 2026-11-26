# Team setup (Windows + Docker Desktop)

This guide sets up the current NEM application on a new machine. Open Electricity NEM is the active dataset. VNM monthly data and CSV ingestion remain legacy; this guide does not restore them into the active workflow. The NEM worker is opt-in and is not started below.

## Requirements

- Windows 10/11 with Docker Desktop and the Docker Compose v2 plugin.
- Git.
- No host Python or Node installation is required for the Docker workflow.

## Clone and configure

```powershell
git clone https://github.com/minhchinh595/126KDLKPDL-Nhom13.git
Set-Location .\126KDLKPDL-Nhom13
Copy-Item .env.example .env
```

Edit `.env` locally. Set a private `POSTGRES_PASSWORD`, a random `JWT_SECRET_KEY` of at least 32 bytes, and separate random internal-service secrets for Analysis, Clustering, Prediction, Classification, and Ingestion. Do not commit `.env`. Use `NEXT_PUBLIC_API_URL=http://localhost:8001` for this local browser setup. The sample database connection uses host `127.0.0.1:5433`, database `electricity_analytics_db`, and user `electricity_app`; inside Compose, Gateway connects to `postgres:5432`.

Build the images and start only PostgreSQL:

```powershell
docker compose build
docker compose up -d postgres
docker compose ps postgres
```

## Initialize the database

Choose exactly one path.

### Restore the sanitized handoff snapshot

Use this path when the team has received `backups/electricity_analytics_nem_handoff_sanitized.dump` through the approved project handoff. On a fresh Compose volume, PostgreSQL creates an empty `electricity_analytics_db` database. Restore before starting application services; do not run migrations first.

```powershell
$backup = ".\backups\electricity_analytics_nem_handoff_sanitized.dump"
if (-not (Test-Path -LiteralPath $backup)) { throw "Handoff backup not found: $backup" }
docker cp $backup electricity-analytics-postgres:/tmp/nem-handoff.dump
docker exec electricity-analytics-postgres pg_restore -U electricity_app -d electricity_analytics_db --no-owner --no-privileges /tmp/nem-handoff.dump
docker exec electricity-analytics-postgres rm -f /tmp/nem-handoff.dump
```

The target database must be a new empty database. `pg_restore` above intentionally does not use `--clean`; never restore over a database containing data. The sanitized snapshot retains NEM observations, NEM dataset/import metadata, ModelRun history, and schema revision, and excludes the source machine's user accounts and VNM dataset rows. Create a new local Admin in the next section.

### Start with an empty database

Use this path only if the team has no handoff snapshot. Apply the checked-in Alembic revisions to the fresh Compose database:

```powershell
docker compose run --rm --no-deps gateway alembic upgrade head
```

This creates schema only; it does not populate NEM observations or trained model results. NEM data must be ingested separately after deliberately configuring Open Electricity access. The NEM worker remains disabled unless explicitly started with its profile.

## Bootstrap the first Admin

Run this once after database initialization. Enter account details in the current PowerShell session; the password is read without echo. The environment variables are passed by name, not as command-line values. The script refuses to create an Admin if one already exists.

```powershell
$env:BOOTSTRAP_ADMIN_USERNAME = Read-Host "Admin username"
$env:BOOTSTRAP_ADMIN_EMAIL = Read-Host "Admin email"
$securePassword = Read-Host "Admin password (12–128 characters)" -AsSecureString
$env:BOOTSTRAP_ADMIN_PASSWORD = [System.Net.NetworkCredential]::new("", $securePassword).Password
try {
    docker compose run --rm --no-deps `
      -e BOOTSTRAP_ADMIN_USERNAME `
      -e BOOTSTRAP_ADMIN_EMAIL `
      -e BOOTSTRAP_ADMIN_PASSWORD `
      gateway python scripts/create_admin.py
}
finally {
    Remove-Item Env:BOOTSTRAP_ADMIN_USERNAME, Env:BOOTSTRAP_ADMIN_EMAIL, Env:BOOTSTRAP_ADMIN_PASSWORD -ErrorAction SilentlyContinue
    $securePassword.Dispose()
}
```

The clear-text password exists briefly in this PowerShell process environment because Docker must receive it. Run on a trusted workstation and clear the variables as shown. Do not place these values in a script, shell history, `.env`, or Docker command arguments. The password is never printed by the bootstrap command.

## Start and verify the application

```powershell
docker compose up -d
docker compose ps
Invoke-RestMethod http://localhost:8001/api/health
```

Open <http://localhost:3000>. Sign in with the Admin created above. The default Compose profile does not start the legacy CSV Ingestion service or NEM worker. Starting `nem-ingestion-worker` makes real API requests and writes to PostgreSQL; only enable that profile after obtaining an Open Electricity key and deliberately approving live ingestion. Do not start the worker merely to restore or view a handoff snapshot.

The API is exposed on `http://localhost:8001`; Frontend on `http://localhost:3000`. The NEM ML services use the separate H2 artifacts and clustering artifact configured under `BE/artifacts/` when those files are available. A database snapshot does not itself contain model binaries. Check the release asset manifest and artifact checksums before using supplied artifacts. If artifacts are not supplied, an Admin must explicitly Train each model before its Run operation can succeed.

## Test database isolation

The test database is a separate opt-in Compose service and volume. Do not use the application database for tests. Follow the test safety instructions in `BE/tests/conftest.py`; the integration fixture recreates schema/data in the database named `electricity_analytics_test`.

## Troubleshooting

- If Compose reports a missing required variable, check the local `.env` without sharing its contents.
- If Gateway is unhealthy, inspect sanitized service logs locally and confirm PostgreSQL is healthy.
- If dashboard data is empty after choosing the empty-database path, that is expected until NEM observations are ingested.
- Do not solve missing model artifacts by copying an H1 artifact over an H2 path.
- Do not enable the `legacy-csv` profile as a substitute for NEM data.
