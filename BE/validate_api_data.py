import json
import subprocess
import pandas as pd
from pathlib import Path
from urllib.request import urlopen

# 1. Doc du lieu CSV
root = Path(__file__).resolve().parent.parent

csv_path = root / "data/processed/vietnam_electricity_demand.csv"

csv_data = pd.read_csv(csv_path)[["month", "value"]]

# 2. Lay du lieu tu API
url = "http://127.0.0.1:8000/api/electricity/demand"

with urlopen(url, timeout=15) as response:
    api_response = json.load(response)

api_data = pd.DataFrame(api_response["records"])

# 3. Lay du lieu tu PostgreSQL
query = """
SELECT to_char(month, 'YYYY-MM') AS month, value
FROM electricity_consumption
WHERE iso3 = 'VNM' AND metric = 'demand'
ORDER BY month;
"""

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

from io import StringIO

db_data = pd.read_csv(StringIO(result))

# 4. Chuan hoa du lieu truoc khi so sanh
def normalize(df):
    df = df[["month", "value"]].copy()
    df["month"] = df["month"].astype(str)
    df["value"] = pd.to_numeric(df["value"]).round(4)

    return df.sort_values("month").reset_index(drop=True)

csv_data = normalize(csv_data)
api_data = normalize(api_data)
db_data = normalize(db_data)

# 5. So sanh
print("===== API DATA VALIDATION =====")

print("CSV records:", len(csv_data))
print("API records:", len(api_data))
print("PostgreSQL records:", len(db_data))

print("API source:", api_response["source"])

print("CSV vs API:", 
      "PASS" if csv_data.equals(api_data) else "FAIL")

print("CSV vs PostgreSQL:",
      "PASS" if csv_data.equals(db_data) else "FAIL")

print("API vs PostgreSQL:",
      "PASS" if api_data.equals(db_data) else "FAIL")

print("===== END VALIDATION =====")