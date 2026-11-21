
import pandas as pd

# Đọc dữ liệu gốc
file_path = "../data/raw/ember-monthly-generation.csv"
df = pd.read_csv(file_path)

# Kiểm tra cấu trúc dữ liệu
print("Các cột:")
print(df.columns.tolist())

print("\nKích thước dataset:", df.shape)

# Lọc dữ liệu Việt Nam
vietnam = df[
    (df["iso3"] == "VNM") &
    (df["metric"] == "demand")
].copy()

# Sắp xếp theo thời gian
vietnam = vietnam.sort_values("month")

print("\nSố dòng dữ liệu Việt Nam:", len(vietnam))
print("\nDữ liệu Việt Nam:")
print(vietnam.head(10))

print("\nThông tin dữ liệu:")
print(vietnam.info())

# Kiểm tra dữ liệu thiếu
print("\nGiá trị thiếu:")
print(vietnam.isnull().sum())

# Xuất file riêng cho Việt Nam
vietnam.to_csv(
    "../data/processed/vietnam_electricity_demand.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\nĐã xuất file dữ liệu Việt Nam thành công!")
