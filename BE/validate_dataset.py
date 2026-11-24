
import pandas as pd
import numpy as np
from pathlib import Path

# 1. Đọc file processed
file_path = (
    Path(__file__).resolve().parent.parent
    / "data/processed/vietnam_electricity_demand.csv"
)

df = pd.read_csv(file_path)

print("===== KIEM TRA CHAT LUONG DU LIEU =====")

# 2. Kiểm tra cấu trúc
print("\nSo dong:", len(df))
print("So cot:", len(df.columns))
print("Ten cot:", df.columns.tolist())

# 3. Kiểm tra quốc gia
print("\nQuoc gia:", df["iso3"].unique())
print("So dong sai quoc gia:", (df["iso3"] != "VNM").sum())

# 4. Kiểm tra chỉ số
print("\nChi so:", df["metric"].unique())
print("So dong sai metric:", (df["metric"] != "demand").sum())

# 5. Kiểm tra đơn vị
print("\nDon vi:", df["unit"].unique())
print("So dong sai don vi:", (df["unit"] != "TWh").sum())

# 6. Kiểm tra thời gian
valid_format = df["month"].astype(str).str.fullmatch(
    r"\d{4}-(0[1-9]|1[0-2])"
)

dates = pd.to_datetime(
    df["month"], format="%Y-%m", errors="coerce"
)

print("\nSo thang sai dinh dang:",
      (~valid_format | dates.isna()).sum())
print("Thang bat dau:", df["month"].min())
print("Thang ket thuc:", df["month"].max())

# 7. Kiểm tra giá trị điện
values = pd.to_numeric(df["value"], errors="coerce")

print("\nGia tri khong hop le:",
      (~np.isfinite(values)).sum())
print("Gia tri am:", (values < 0).sum())
print("Gia tri bang 0:", (values == 0).sum())
print("Gia tri nho nhat:", values.min())
print("Gia tri lon nhat:", values.max())

# 8. Kiểm tra dữ liệu thiếu
print("\nDu lieu thieu:")
print(df.isnull().sum())

print("\nSo dong thieu truong bat buoc:",
      df.drop(columns=["fuel"]).isnull().any(axis=1).sum())

print("So dong fuel khong rong:",
      df["fuel"].notna().sum())

# 9. Kiểm tra dữ liệu trùng
keys = ["country_id", "month", "metric", "fuel"]

print("\nSo dong trung hoan toan:",
      df.duplicated().sum())

print("So dong trung khoa:",
      df.duplicated(subset=keys).sum())

# 10. Kiểm tra tháng bị thiếu
if dates.notna().any():
    expected_months = pd.period_range(
        start=dates.min(),
        end=dates.max(),
        freq="M"
    )

    actual_months = pd.PeriodIndex(
        dates.dropna(), freq="M"
    )

    missing_months = expected_months.difference(actual_months)

    print("\nSo thang bi thieu:", len(missing_months))
    print("Danh sach thang thieu:", missing_months.tolist())

print("\n===== KET THUC KIEM TRA =====")
