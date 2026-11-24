
# DATA DICTIONARY

## 1. Tổng quan dữ liệu

- Dự án: Electricity Consumption Analytics
- Nguồn: Ember Monthly Electricity Data
- Quốc gia: Vietnam (VNM)
- Chỉ số: Electricity demand
- Đơn vị: TWh
- Tần suất: Hàng tháng
- Thời gian: 01/2019 - 09/2026
- Số bản ghi gốc: 99.247
- Số bản ghi sau xử lý: 93
- Số cột CSV: 8
- Database: PostgreSQL
- Schema revision: 20261122_0001

## 2. Nguồn và đường dẫn dữ liệu

Raw data:
data/raw/ember-monthly-generation.csv

Processed data:
data/processed/vietnam_electricity_demand.csv

Script trích xuất:
BE/check_dataset.py

Script kiểm tra chất lượng:
BE/validate_dataset.py

Script import:
BE/scripts/import_electricity_data.py

## 3. Cấu trúc file CSV

| Field | Data type | Required | Description | Example |
|---|---|---|---|---|
| country_id | String | Yes | Mã định danh quốc gia | vietnam |
| country | String | Yes | Tên quốc gia | Vietnam |
| iso3 | String | Yes | Mã quốc gia ISO 3 ký tự | VNM |
| month | String | Yes | Tháng thống kê YYYY-MM | 2019-01 |
| metric | String | Yes | Chỉ số nhu cầu điện | demand |
| fuel | String | No | Loại nhiên liệu | NULL |
| value | Numeric | Yes | Giá trị nhu cầu điện | 17.87 |
| unit | String | Yes | Đơn vị đo | TWh |

Lưu ý: Cột fuel phải tồn tại trong CSV nhưng
được phép để trống. Với dataset demand hiện tại,
fuel luôn để trống.

## 4. Database Schema

### 4.1. Table: datasets

Quản lý metadata của bộ dữ liệu.

| Field | PostgreSQL type | Nullable | Description |
|---|---|---|---|
| id | INTEGER | No | Primary key |
| name | VARCHAR(160) | No | Tên dataset |
| source | VARCHAR(255) | No | Nguồn dữ liệu |
| file_name | VARCHAR(255) | No | Tên file CSV |
| description | TEXT | Yes | Mô tả dataset |
| record_count | INTEGER | No | Số bản ghi |
| start_date | DATE | Yes | Thời gian bắt đầu |
| end_date | DATE | Yes | Thời gian kết thúc |
| status | VARCHAR(30) | No | Trạng thái dataset |
| created_at | TIMESTAMPTZ | No | Thời điểm tạo |
| updated_at | TIMESTAMPTZ | No | Thời điểm cập nhật |

Constraints:
- Primary key: id
- Unique: (name, source)
- record_count mặc định: 0
- status mặc định: ready

### 4.2. Table: electricity_consumption

Lưu dữ liệu nhu cầu điện theo tháng.

| Field | PostgreSQL type | Nullable | Description |
|---|---|---|---|
| id | INTEGER | No | Primary key |
| dataset_id | INTEGER | No | Foreign key đến datasets.id |
| country_id | VARCHAR(80) | No | Mã định danh quốc gia |
| country | VARCHAR(120) | No | Tên quốc gia |
| iso3 | VARCHAR(3) | No | Mã quốc gia ISO |
| month | DATE | No | Ngày đầu tiên của tháng |
| metric | VARCHAR(80) | No | Chỉ số điện |
| fuel | VARCHAR(80) | Yes | Loại nhiên liệu |
| value | NUMERIC(14,4) | No | Giá trị nhu cầu điện |
| unit | VARCHAR(30) | No | Đơn vị đo |
| created_at | TIMESTAMPTZ | No | Thời điểm tạo |

Constraints:
- Primary key: id
- Foreign key: dataset_id
- Reference: datasets.id
- ON DELETE CASCADE
- CHECK: value >= 0
- Unique natural key:
  country_id, month, metric, COALESCE(fuel, '')

Indexes:
- ix_electricity_month
- ix_electricity_country_month
- ix_electricity_metric_month
- uq_electricity_natural_key

## 5. Data Transformation

- Lọc quốc gia theo iso3 = VNM.
- Lọc chỉ số metric = demand.
- Sắp xếp dữ liệu theo thời gian.
- Giữ nguyên đơn vị TWh.
- Giữ nguyên giá trị nhu cầu điện.
- Chuyển fuel trống thành NULL khi import.
- Chuyển month từ YYYY-MM sang DATE.
- Ví dụ: 2019-01 thành 2019-01-01.
- Không ghi đè dữ liệu raw.

## 6. Data Quality Report

| Validation | Result | Status |
|---|---|---|
| Total processed rows | 93 | PASS |
| Total columns | 8 | PASS |
| Invalid country | 0 | PASS |
| Invalid metric | 0 | PASS |
| Invalid unit | 0 | PASS |
| Invalid month format | 0 | PASS |
| Invalid numeric value | 0 | PASS |
| Negative value | 0 | PASS |
| Zero value | 0 | PASS |
| Missing required values | 0 | PASS |
| Missing fuel | 93 | VALID |
| Duplicate natural key | 0 | PASS |
| Missing month | 0 | PASS |

Minimum value: 16.11 TWh

Maximum value: 32.84 TWh

## 7. Sample Data

| country | month | metric | value | unit |
|---|---|---|---|---|
| Vietnam | 2019-01 | demand | 17.87 | TWh |
| Vietnam | 2019-02 | demand | 18.89 | TWh |
| Vietnam | 2019-03 | demand | 16.11 | TWh |
| Vietnam | 2019-04 | demand | 20.00 | TWh |
| Vietnam | 2019-05 | demand | 20.86 | TWh |

## 8. Database Connection

- DBMS: PostgreSQL 16
- Host: 127.0.0.1
- Port: 5433
- Database: electricity_analytics_db
- Username: electricity_app
- Password: Configured locally in .env

Không lưu mật khẩu trong repository.

## 9. Import Process

Tại thư mục gốc:

docker compose up -d postgres

Tại thư mục BE, sau khi kích hoạt môi trường Python:

python -m pip install -r requirements.txt

alembic upgrade head

alembic current

python scripts/import_electricity_data.py


## 10. Database Validation

Verification date: 2026-11-24

- Dataset metadata: 1 record
- Dataset status: imported
- Metadata record_count: 93
- Actual consumption count: 93
- CSV rows validated: 93
- Records inserted: 93
- Duplicate records skipped (first import): 0
- First five records comparison: PASS
- Database migration: 20261122_0001 (head)
- Re-import validation: PASS
- Records inserted on re-import: 0
- Duplicate records skipped on re-import: 93
- Backend integration: Pending
- Backend startup: PASS
- Health Check API: PASS
- Electricity Demand API: PASS
- API record count: 93
- CSV vs API: PASS
- CSV vs PostgreSQL: PASS
- API vs PostgreSQL: PASS
- Data consistency validation: PASS
- PostgreSQL integration: Pending verification

## 11. Data Limitations

- Dữ liệu chỉ bao gồm Việt Nam.
- Dữ liệu có độ phân giải theo tháng.
- Không có dữ liệu theo tỉnh thành.
- Không có dữ liệu theo hộ gia đình.
- Không phân loại nhu cầu điện theo nhiên liệu.
- Không có dữ liệu theo giờ hoặc ngày.
- Chỉ có 93 quan sát cho phân tích và dự báo.

## 12. Handover Status

- Raw data: Completed
- Processed data: Completed
- CSV validation: Completed
- PostgreSQL setup: Completed
- Database migration: Completed
- Dataset metadata: Verified
- Database record validation: Completed
- Re-import validation: Completed
- API validation: Completed
- Data consistency validation: Completed
- PostgreSQL integration: Pending verification
