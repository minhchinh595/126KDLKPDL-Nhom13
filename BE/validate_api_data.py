
import json
import subprocess
import pandas as pd

from pathlib import Path
from io import StringIO
from getpass import getpass
from http.cookiejar import CookieJar
from urllib.request import (
    Request,
    build_opener,
    HTTPCookieProcessor
)
from urllib.error import HTTPError, URLError


# 1. Cau hinh
root = Path(__file__).resolve().parent.parent

csv_path = root / "data/processed/vietnam_electricity_demand.csv"

base_url = "http://127.0.0.1:8000"
expected_source = "PostgreSQL: electricity_consumption"
expected_count = 93

print("===== API DATA VALIDATION =====")


# 2. Doc du lieu CSV
csv_data = pd.read_csv(csv_path)[["month", "value"]]


# 3. Dang nhap API
email = input("Admin email: ").strip()
password = getpass("Admin password: ")

cookie_jar = CookieJar()

opener = build_opener(
    HTTPCookieProcessor(cookie_jar)
)

login_data = json.dumps({
    "email": email,
    "password": password
}).encode("utf-8")

login_request = Request(
    f"{base_url}/api/auth/login",
    data=login_data,
    headers={
        "Content-Type": "application/json"
    },
    method="POST"
)

try:
    with opener.open(login_request, timeout=15) as response:
        login_response = json.load(response)

    print("API login: PASS")

except (HTTPError, URLError) as error:
    print("API login: FAIL")
    print("Error:", error)
    raise SystemExit(1)

finally:
    del password
    del login_data


# 4. Lay du lieu tu API va xu ly phan trang
records = []
page = 1
page_size = 30
source_valid = True
metadata_valid = True
pagination_valid = True
total_matches = None

try:
    while True:
        url = (
            f"{base_url}/api/electricity/demand"
            f"?page={page}&page_size={page_size}"
        )

        with opener.open(url, timeout=15) as response:
            api_response = json.load(response)

        if api_response["source"] != expected_source:
            source_valid = False

        if (
            api_response["country"] != "Vietnam"
            or api_response["iso3"] != "VNM"
            or api_response["unit"] != "TWh"
        ):
            metadata_valid = False

        if total_matches is None:
            total_matches = api_response["total_matches"]

        page_records = api_response["records"]

        if (
            api_response["page"] != page
            or api_response["page_size"] != page_size
            or api_response["total_matches"] != total_matches
            or api_response["total"] != len(page_records)
        ):
            pagination_valid = False
            break

        records.extend(page_records)

        if len(records) >= total_matches:
            break

        if not page_records:
            pagination_valid = False
            break

        page += 1

except (HTTPError, URLError) as error:
    print("API request: FAIL")
    print("Error:", error)
    raise SystemExit(1)

api_data = pd.DataFrame(
    records,
    columns=["id", "month", "value"]
)


# 5. Lay du lieu tu PostgreSQL
query = """
SELECT to_char(month, 'YYYY-MM') AS month, value
FROM electricity_consumption
WHERE iso3 = 'VNM'
    AND metric = 'demand'
    AND fuel IS NULL
    AND unit = 'TWh'
ORDER BY month;
"""

try:
    result = subprocess.check_output(
        [
            "docker", "compose", "exec", "-T",
            "postgres", "psql",
            "-U", "electricity_app",
            "-d", "electricity_analytics_db",
            "--csv", "-c", query
        ],
        cwd=root,
        text=True
    )

except subprocess.CalledProcessError as error:
    print("PostgreSQL query: FAIL")
    print("Error:", error)
    raise SystemExit(1)

db_data = pd.read_csv(StringIO(result))


# 6. Chuan hoa du lieu truoc khi so sanh
def normalize(df):
    df = df[["month", "value"]].copy()

    df["month"] = pd.to_datetime(
        df["month"],
        format="%Y-%m"
    ).dt.strftime("%Y-%m")

    df["value"] = (
        pd.to_numeric(df["value"])
        .astype(float)
        .round(4)
    )

    return df.sort_values("month").reset_index(drop=True)


csv_data = normalize(csv_data)
api_data = normalize(api_data)
db_data = normalize(db_data)


# 7. Kiem tra so luong va tinh toan ven
count_valid = (
    len(csv_data)
    == len(api_data)
    == len(db_data)
    == total_matches
    == expected_count
)

duplicate_valid = all(
    not df["month"].duplicated().any()
    for df in [csv_data, api_data, db_data]
)

missing_valid = all(
    not df.isna().any().any()
    for df in [csv_data, api_data, db_data]
)

expected_months = pd.period_range(
    start="2019-01",
    end="2026-09",
    freq="M"
).astype(str).tolist()

month_range_valid = all(
    df["month"].tolist() == expected_months
    for df in [csv_data, api_data, db_data]
)


# 8. So sanh du lieu
csv_api_valid = csv_data.equals(api_data)
csv_db_valid = csv_data.equals(db_data)
api_db_valid = api_data.equals(db_data)


# 9. In ket qua
def status(result):
    return "PASS" if result else "FAIL"


print("\n===== VALIDATION RESULTS =====")

print("CSV records:", len(csv_data))
print("API records:", len(api_data))
print("PostgreSQL records:", len(db_data))

print("API source:", api_response["source"])

checks = {
    "API source validation": source_valid,
    "API metadata validation": metadata_valid,
    "Pagination validation": pagination_valid,
    "Record count validation": count_valid,
    "Duplicate month validation": duplicate_valid,
    "Missing value validation": missing_valid,
    "Month range validation": month_range_valid,
    "CSV vs API": csv_api_valid,
    "CSV vs PostgreSQL": csv_db_valid,
    "API vs PostgreSQL": api_db_valid
}

for name, passed in checks.items():
    print(f"{name}: {status(passed)}")

overall_result = all(checks.values())

print("------------------------------")
print("OVERALL RESULT:", status(overall_result))
print("===== END VALIDATION =====")

raise SystemExit(0 if overall_result else 1)