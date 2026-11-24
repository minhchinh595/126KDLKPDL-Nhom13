
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
- Database: PostgreSQL 16
- Schema revision: 20261124_0002 (head)
- Tổng số bảng database: 6
- Nguồn dữ liệu của Electricity Demand API: PostgreSQL

## 2. Nguồn và đường dẫn dữ liệu

| Thành phần | Đường dẫn |
|---|---|
| Raw data | `data/raw/ember-monthly-generation.csv` |
| Processed data | `data/processed/vietnam_electricity_demand.csv` |
| Script trích xuất | `BE/check_dataset.py` |
| Script kiểm tra chất lượng | `BE/validate_dataset.py` |
| Script import | `BE/scripts/import_electricity_data.py` |
| Script kiểm tra tích hợp API | `BE/validate_api_data.py` |
| Database migrations | `BE/alembic/versions/` |
| Database design | `docs/database-design.md` |

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

Lưu ý:

- Cột fuel phải tồn tại trong CSV nhưng được phép để trống.
- Với dataset demand hiện tại, fuel luôn để trống.
- Giá trị fuel trống được chuyển thành NULL khi import vào PostgreSQL.

## 4. Database Schema

Database hiện tại gồm 6 bảng:

| Table | Purpose |
|---|---|
| alembic_version | Quản lý phiên bản database migration |
| datasets | Quản lý metadata của dataset |
| electricity_consumption | Lưu dữ liệu tiêu thụ điện |
| dataset_imports | Quản lý lịch sử import dataset |
| model_runs | Quản lý các lần chạy mô hình |
| users | Quản lý tài khoản người dùng |

Data Dictionary tập trung mô tả chi tiết ba bảng thuộc phạm vi quản lý dữ liệu.

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
| storage_key | VARCHAR(80) | Yes | Khóa định danh lưu trữ dataset |

Constraints:

- Primary key: id
- Unique: (name, source)
- Unique: storage_key
- record_count mặc định: 0
- status mặc định: ready
- created_at mặc định: now()
- updated_at mặc định: now()

Unique constraints:

- uq_datasets_name_source
- uq_datasets_storage_key

Cột storage_key được bổ sung trong migration
20261124_0002 và cho phép NULL để tương thích
với các dataset đã tồn tại.

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
- created_at mặc định: now()

Unique natural key:

country_id, month, metric, COALESCE(fuel, '')

Indexes:

- ix_electricity_month
- ix_electricity_country_month
- ix_electricity_metric_month
- uq_electricity_natural_key

### 4.3. Table: dataset_imports

Lưu lịch sử thực hiện import dữ liệu, hỗ trợ theo dõi
kết quả và các lỗi phát sinh trong quá trình import.

Bảng được bổ sung trong migration 20261124_0002.

| Field | PostgreSQL type | Nullable | Description |
|---|---|---|---|
| id | INTEGER | No | Primary key |
| dataset_id | INTEGER | No | Foreign key đến datasets.id |
| mode | VARCHAR(20) | No | Chế độ import |
| status | VARCHAR(20) | No | Trạng thái import |
| rows_read | INTEGER | No | Số dòng đã đọc |
| inserted_count | INTEGER | No | Số bản ghi được thêm |
| updated_count | INTEGER | No | Số bản ghi được cập nhật |
| skipped_count | INTEGER | No | Số bản ghi bị bỏ qua |
| error_count | INTEGER | No | Số lỗi được ghi nhận |
| error_message | TEXT | Yes | Nội dung lỗi |
| started_at | TIMESTAMPTZ | No | Thời điểm bắt đầu |
| completed_at | TIMESTAMPTZ | Yes | Thời điểm hoàn thành |

Constraints:

- Primary key: id
- Foreign key: dataset_id
- Reference: datasets.id
- ON DELETE CASCADE
- rows_read mặc định: 0
- inserted_count mặc định: 0
- updated_count mặc định: 0
- skipped_count mặc định: 0
- error_count mặc định: 0
- started_at mặc định: now()

Indexes:

- ix_dataset_imports_dataset_id
- ix_dataset_imports_started_at

Lưu ý:

- Migration tạo bảng lịch sử import nhưng không
  tự động tạo lại lịch sử cho các lần import trước đó.
- Cấu trúc bảng đã được kiểm tra trực tiếp trong PostgreSQL.
- Chức năng ghi lịch sử import qua API chưa được
  kiểm thử trong phạm vi nghiệm thu hiện tại.

### 4.4. Database Relationships

| Parent table | Child table | Relationship | Foreign key |
|---|---|---|---|
| datasets | electricity_consumption | 1:N | dataset_id |
| datasets | dataset_imports | 1:N | dataset_id |

Cả hai quan hệ sử dụng ON DELETE CASCADE.

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

- Minimum value: 16.11 TWh
- Maximum value: 32.84 TWh
- First month: 2019-01
- Last month: 2026-09

## 7. Sample Data

| country | month | metric | value | unit |
|---|---|---|---|---|
| Vietnam | 2019-01 | demand | 17.87 | TWh |
| Vietnam | 2019-02 | demand | 18.89 | TWh |
| Vietnam | 2019-03 | demand | 16.11 | TWh |
| Vietnam | 2019-04 | demand | 20.00 | TWh |
| Vietnam | 2019-05 | demand | 20.86 | TWh |

## 8. Database Connection

| Configuration | Value |
|---|---|
| DBMS | PostgreSQL 16 |
| Docker service | postgres |
| Container | electricity-analytics-postgres |
| Local host | 127.0.0.1 |
| Local port | 5433 |
| Docker internal host | postgres |
| Docker internal port | 5432 |
| Database | electricity_analytics_db |
| Username | electricity_app |
| Password | Configured locally in .env |
| Docker volume | electricity_analytics_postgres_data |

Security:

- Không lưu mật khẩu trong repository.
- Không hardcode mật khẩu trong script validation.
- File .env được Git bỏ qua.
- API sử dụng JWT trong HttpOnly Cookie.
- Các secret được cấu hình trong môi trường local.

## 9. Import and Validation Process

### 9.1. Start PostgreSQL

Tại thư mục gốc:

```powershell
docker compose up -d postgres
```

### 9.2. Install Backend dependencies

Tại thư mục BE, sau khi kích hoạt môi trường Python:

```powershell
python -m pip install -r requirements.txt
```

### 9.3. Apply database migrations

```powershell
alembic upgrade head
alembic current
```

Expected revision:

20261124_0002 (head)

### 9.4. Validate processed dataset

```powershell
python validate_dataset.py
```

### 9.5. Import dataset

```powershell
python scripts/import_electricity_data.py
```

### 9.6. Start Backend Gateway

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file ..\.env
```

### 9.7. Validate API integration

Mở Terminal khác, kích hoạt môi trường Python
và chuyển đến thư mục BE:

```powershell
python validate_api_data.py
```

Nhập thông tin tài khoản local khi được yêu cầu.

Script thực hiện:

- Đăng nhập qua API.
- Duy trì Cookie xác thực.
- Truy xuất dữ liệu Electricity Demand.
- Hỗ trợ phân trang.
- Kiểm tra nguồn dữ liệu PostgreSQL.
- Kiểm tra metadata.
- Đối chiếu số lượng bản ghi.
- Kiểm tra dữ liệu thiếu và trùng lặp.
- Đối chiếu từng tháng và giá trị giữa CSV,
  PostgreSQL và API sau khi chuẩn hóa đến
  4 chữ số thập phân.

## 10. Database and API Validation

### 10.1. Database Validation

Verification date: 2026-11-24

| Validation | Result | Status |
|---|---|---|
| Dataset metadata | 1 record | PASS |
| Dataset status | imported | PASS |
| Metadata record_count | 93 | PASS |
| Actual consumption count | 93 | PASS |
| Initial inserted records | 93 | PASS |
| Initial skipped records | 0 | PASS |
| Re-import inserted records | 0 | PASS |
| Re-import skipped records | 93 | PASS |
| Database migration | 20261124_0002 (head) | PASS |
| Total database tables | 6 | PASS |
| dataset_imports schema | Verified | PASS |
| datasets.storage_key | Verified | PASS |
| Records after migration | 93 | PASS |

Các kết quả import và re-import được ghi nhận
trong lần kiểm thử trước khi nâng cấp migration 0002.

### 10.2. Backend Integration

| Endpoint | Method | Result |
|---|---|---|
| /api/health | GET | 200 OK |
| /api/health/ready | GET | 200 OK |
| /api/auth/login | POST | 200 OK |
| /api/auth/me | GET | 200 OK |
| /api/electricity/demand | GET | 200 OK |

Backend database status: connected

API data source:

PostgreSQL: electricity_consumption

### 10.3. Data Consistency Validation

| Validation | Result |
|---|---|
| CSV records | 93 |
| PostgreSQL records | 93 |
| API records | 93 |
| API login | PASS |
| API source validation | PASS |
| API metadata validation | PASS |
| Pagination validation (4 pages, page_size=30) | PASS |
| Record count validation | PASS |
| Duplicate month validation | PASS |
| Missing value validation | PASS |
| Month range validation | PASS |
| CSV vs API | PASS |
| CSV vs PostgreSQL | PASS |
| API vs PostgreSQL | PASS |

Conclusion:

- PostgreSQL integration: Verified
- Data consistency validation: PASS
- All 93 month-value pairs are consistent across
  CSV, PostgreSQL and API after normalization.
- Multi-page pagination validation: PASS
- Page size: 30
- Expected number of pages: 4
- Total retrieved records: 93
- Overall validation result: PASS
- Validation exit code: 0

## 11. Data Limitations

- Dữ liệu chỉ bao gồm Việt Nam.
- Dữ liệu có độ phân giải theo tháng.
- Không có dữ liệu theo tỉnh thành.
- Không có dữ liệu theo hộ gia đình.
- Không phân loại nhu cầu điện theo nhiên liệu.
- Không có dữ liệu theo giờ hoặc ngày.
- Chỉ có 93 quan sát cho phân tích và dự báo.
- Script validation sử dụng số lượng và khoảng
  thời gian kỳ vọng của dataset hiện tại.
- Khi dataset được mở rộng, cần cập nhật các
  giá trị kỳ vọng trong script validation.
- Chức năng upload, sync và ghi lịch sử import
  qua API chưa được nghiệm thu trong phạm vi này.
- Frontend và các microservice phân tích, dự báo,
  phân cụm, phân loại không thuộc phạm vi kiểm
  thử tích hợp dữ liệu hiện tại.

## 12. Handover Status

| Deliverable | Status |
|---|---|
| Raw data | Completed |
| Processed data | Completed |
| CSV validation | Completed |
| PostgreSQL setup | Completed |
| Database migration | Completed |
| Dataset metadata | Verified |
| Database record validation | Completed |
| Re-import validation | Completed |
| Database schema validation | Completed |
| API authentication | Completed |
| API validation | Completed |
| Data consistency validation | Completed |
| PostgreSQL integration | Verified |
| Multi-page pagination testing | Completed |
| Dataset import history schema | Verified |
| Dataset import history functional testing | Not tested |
| Data Dictionary | Updated |
| Database Design | Updated |
| Git Pull Request | Pending |
