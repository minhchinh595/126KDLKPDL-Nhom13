"""Run real Gateway integration checks locally. Never accesses the DB or services directly."""
import argparse
import getpass
import http.cookiejar
import json
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPCookieProcessor


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, path, method="GET", body=None, expected=(200,), raw=None, headers=None):
        payload = raw if raw is not None else json.dumps(body).encode() if body is not None else None
        request_headers = headers or ({"Content-Type": "application/json"} if body is not None else {})
        request = Request(self.base + path, data=payload, method=method, headers=request_headers)
        try:
            with self.opener.open(request, timeout=180 if method == "POST" else 10) as response:
                status, content = response.status, response.read()
        except HTTPError as error:
            status, content = error.code, error.read()
        if status not in expected:
            # Do not write request bodies, passwords or cookies to reports.
            raise RuntimeError(f"{method} {path}: expected {expected}, received HTTP {status}")
        return json.loads(content) if content else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", default="http://localhost:8001")
    parser.add_argument("--exercise-writes", action="store_true", help="Create Analyst if needed, upload/import the real CSV, train and run all models via Gateway")
    parser.add_argument("--output", type=Path, default=Path("test-results/gateway-e2e.json"))
    args = parser.parse_args()
    report = {"gateway": args.gateway, "status": "running", "checks": [], "scope": "Real HTTP Gateway integration; browser UI is a separate check"}

    def check(label, action):
        action()
        report["checks"].append({"name": label, "status": "passed"})
        print("PASS", label)

    try:
        client = Client(args.gateway)
        def health():
            result = client.request("/api/health")
            if result.get("status") != "success" or result.get("database") != "connected":
                raise RuntimeError("Gateway health did not confirm the database connection")
        check("Gateway / DB health", health)
        spec = client.request("/openapi.json")
        required = ["/api/auth/me", "/api/users", "/api/dashboard/overview", "/api/datasets/upload", "/api/datasets/{dataset_id}", "/api/datasets/{dataset_id}/import", "/api/model-runs", "/api/model-runs/{run_id}"]
        if any(path not in spec["paths"] for path in required):
            raise RuntimeError("Live OpenAPI does not match the frontend contract")
        check("Anonymous demand denied", lambda: client.request("/api/electricity/demand", expected=(401,)))
        email = input("Admin email: ").strip()
        password = getpass.getpass("Admin password (hidden): ")
        client.request("/api/auth/login", "POST", {"email": email, "password": password})
        del password
        if client.request("/api/auth/me")["role"] != "admin":
            raise RuntimeError("An Admin session is required")
        report["checks"].append({"name": "Admin login and session", "status": "passed"})
        for path in ["/api/dashboard/overview", "/api/electricity/demand?page=1&page_size=1000", "/api/analysis/summary", "/api/analysis/trend?window_months=6", "/api/analysis/seasonality", "/api/analysis/correlation", "/api/analysis/distribution?bins=5", "/api/datasets", "/api/datasets/sync/status"]:
            check("Admin GET " + path, lambda path=path: client.request(path))
        if args.exercise_writes:
            analyst_email = input("Analyst test email (new or existing): ").strip()
            analyst_password = getpass.getpass("Analyst test password (12+ chars, hidden): ")
            if len(analyst_password) < 12:
                raise RuntimeError("Analyst password must be at least 12 characters")
            users = client.request("/api/users?" + urlencode({"search": analyst_email, "page_size": 100}))["items"]
            existing = next((user for user in users if user["email"].lower() == analyst_email.lower()), None)
            if existing:
                if existing["role"] != "analyst" or not existing["is_active"]:
                    raise RuntimeError("The supplied test account must be an active Analyst")
            else:
                client.request("/api/users", "POST", {"username": "analyst_e2e_" + uuid.uuid4().hex[:8], "email": analyst_email, "password": analyst_password, "role": "analyst"}, expected=(201,))
            csv_path = Path(__file__).resolve().parents[2] / "data/processed/vietnam_electricity_demand.csv"
            boundary = "----GatewayE2E" + uuid.uuid4().hex
            fields = {"name": "E2E real dataset " + uuid.uuid4().hex[:8], "source": "project-csv-integration-check"}
            chunks = []
            for key, value in fields.items():
                chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
            chunks += [f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="demand.csv"\r\nContent-Type: text/csv\r\n\r\n'.encode(), csv_path.read_bytes(), f'\r\n--{boundary}--\r\n'.encode()]
            dataset = client.request("/api/datasets/upload", "POST", raw=b"".join(chunks), headers={"Content-Type": "multipart/form-data; boundary=" + boundary}, expected=(201,))
            check("Dataset detail", lambda: client.request(f"/api/datasets/{dataset['id']}"))
            check("CSV import", lambda: client.request(f"/api/datasets/{dataset['id']}/import", "POST"))
            check("CSV import history", lambda: client.request(f"/api/datasets/{dataset['id']}/history"))
            for kind in ["clustering", "prediction", "classification"]:
                check(kind + " training", lambda kind=kind: client.request(f"/api/{kind}/train", "POST"))
                check(kind + " run", lambda kind=kind: client.request(f"/api/{kind}/run", "POST"))
                check(kind + " latest", lambda kind=kind: client.request(f"/api/{kind}/latest"))
                runs = client.request(f"/api/{kind}/runs")
                if not runs["items"]:
                    raise RuntimeError(kind + " history is empty after run")
                check(kind + " run detail", lambda kind=kind, run_id=runs["items"][0]["id"]: client.request(f"/api/{kind}/runs/{run_id}"))
                central = client.request("/api/model-runs?" + urlencode({"model_type": kind, "status": "completed", "order": "desc", "page": 1, "page_size": 10}))
                if not central["items"] or any(run["model_type"] != kind or run["status"] != "completed" for run in central["items"]):
                    raise RuntimeError("Model Management filters returned unexpected runs")
                check(kind + " central history detail", lambda run_id=central["items"][0]["id"]: client.request(f"/api/model-runs/{run_id}"))
            analyst = Client(args.gateway)
            analyst.request("/api/auth/login", "POST", {"email": analyst_email, "password": analyst_password})
            del analyst_password
            if analyst.request("/api/auth/me")["role"] != "analyst":
                raise RuntimeError("Analyst login returned the wrong role")
            check("Analyst Model Management", lambda: analyst.request("/api/model-runs"))
            check("Analyst dataset detail", lambda: analyst.request(f"/api/datasets/{dataset['id']}"))
            for path in ["/api/dashboard/overview", "/api/analysis/summary", "/api/datasets", "/api/clustering/latest", "/api/prediction/latest", "/api/classification/latest"]:
                check("Analyst GET " + path, lambda path=path: analyst.request(path))
            for path in ["/api/clustering/train", "/api/clustering/run", "/api/prediction/train", "/api/prediction/run", "/api/classification/train", "/api/classification/run", "/api/datasets/sync"]:
                check("Analyst forbidden " + path, lambda path=path: analyst.request(path, "POST", expected=(403,)))
            check("Analyst forbidden import", lambda: analyst.request(f"/api/datasets/{dataset['id']}/import", "POST", expected=(403,)))
            check("Analyst forbidden upload", lambda: analyst.request("/api/datasets/upload", "POST", raw=b"".join(chunks), headers={"Content-Type": "multipart/form-data; boundary=" + boundary}, expected=(403,)))
            check("Analyst cannot manage users", lambda: analyst.request("/api/users", expected=(403,)))
            analyst.request("/api/auth/logout", "POST", expected=(204,))
            check("Analyst logout invalidates session", lambda: analyst.request("/api/auth/me", expected=(401,)))
            report["analyst_email"] = analyst_email
        client.request("/api/auth/logout", "POST", expected=(204,))
        check("Admin logout invalidates session", lambda: client.request("/api/auth/me", expected=(401,)))
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "blocked" if not report["checks"] else "failed"
        report["error"] = str(error)
        print("BLOCKED/FAILED:", report["error"], file=sys.stderr)
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Report:", args.output)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
