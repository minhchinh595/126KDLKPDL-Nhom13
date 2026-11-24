"""Prompt for test credentials locally, then run the real browser suite without storing passwords."""
import argparse
import getpass
import os
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--exercise-writes", action="store_true", help="Create Analyst if needed, upload/import CSV, train and run models through the UI")
args = parser.parse_args()
frontend = Path(__file__).resolve().parents[1]
if not (frontend / "node_modules/@playwright/test").exists():
    print("Install browser test dependencies from FE first:\nnpm install --save-dev @playwright/test\nnpx playwright install chromium", file=sys.stderr)
    raise SystemExit(1)
environment = os.environ.copy()
environment["E2E_ADMIN_EMAIL"] = input("Admin email: ").strip()
environment["E2E_ADMIN_PASSWORD"] = getpass.getpass("Admin password (hidden): ")
environment["E2E_EXERCISE_WRITES"] = "1" if args.exercise_writes else "0"
if args.exercise_writes:
    environment["E2E_ANALYST_EMAIL"] = input("Analyst test email (new or existing): ").strip()
    environment["E2E_ANALYST_PASSWORD"] = getpass.getpass("Analyst test password (12+ chars, hidden): ")
    if len(environment["E2E_ANALYST_PASSWORD"]) < 12:
        raise SystemExit("Analyst password must be at least 12 characters")
# Fixed command text: user inputs go only through the subprocess environment.
result = subprocess.run("npm run test:e2e", shell=True, cwd=frontend, env=environment)
raise SystemExit(result.returncode)
