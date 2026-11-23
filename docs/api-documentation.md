# Backend API và kết nối Frontend

Backend hiện đọc dữ liệu điện từ PostgreSQL, không đọc CSV trực tiếp trong request. Router được đăng ký trong `BE/app/main.py`; OpenAPI có endpoint health, auth, users, datasets, electricity, dashboard, analysis, model runs và reports.

## Authentication, cookie và CORS

- `POST /api/auth/login`: nhận `{ "email": "...", "password": "..." }`, trả thông tin user công khai và đặt JWT trong HttpOnly cookie.
- `POST /api/auth/logout`: xóa cookie.
- `GET /api/auth/me`: trả user hiện tại.
- Cookie sống theo `ACCESS_TOKEN_TTL_MINUTES`; `APP_ENV=production` bật `Secure`. JWT secret chỉ đặt trong environment, tối thiểu 32 bytes; không đưa vào Git hoặc Frontend.
- Endpoint dữ liệu, dashboard, analysis, model-result reads và reports yêu cầu Analyst hoặc Admin. Quản lý user/dataset và chạy/train model chỉ dành cho Admin.
- Frontend gọi API khác origin phải bật gửi cookie: `fetch(..., { credentials: "include" })` hoặc Axios `withCredentials: true`. Backend cho phép credentials và origins mặc định `http://localhost:3000`, `http://127.0.0.1:3000`; origin bổ sung khai báo trong `CORS_ORIGINS`.

## Dữ liệu điện

### `GET /api/electricity/demand`

Đọc dữ liệu tháng `VNM / demand / fuel IS NULL / TWh` từ `electricity_consumption`. Hỗ trợ `start_month`, `end_month`, `page` (mặc định 1), `page_size` (mặc định 100, tối đa 1000). Phản hồi có `records` (gồm `id`, `month`, `value`), `total` của trang, `total_matches`, `start_month`, `end_month`, nguồn và đơn vị. API yêu cầu cookie Analyst/Admin.

Các endpoint dữ liệu khác: `/api/electricity/demand/statistics`, `/api/electricity/demand/{record_id}`, `/api/electricity/demand/export`.

## Analysis, dashboard và reports

- Dashboard: `GET /api/dashboard/overview`.
- Analysis: `GET /api/analysis/summary`, `/trend`, `/seasonality`, `/correlation`, `/distribution`.
- Reports: `GET /api/reports/summary`, `/analysis`, `/model-runs`, `/export`.
- Analysis được tính từ dữ liệu nguồn khi gọi API; hiện không lưu thành bảng pattern riêng.

## Model training, run và lịch sử

Train và run là hai thao tác tách biệt. Chỉ Admin được gọi train/run; Analyst được đọc kết quả/lịch sử.

| Model | Train (build artifact) | Run (nạp artifact, tạo kết quả) | Latest/history |
|---|---|---|---|
| Clustering K-Means | `POST /api/clustering/train` | `POST /api/clustering/run` | `GET /api/clustering/latest`, `/runs`, `/runs/{id}` |
| Prediction | `POST /api/prediction/train` | `POST /api/prediction/run` | `GET /api/prediction/latest`, `/runs`, `/runs/{id}` |
| Classification | `POST /api/classification/train` | `POST /api/classification/run` | `GET /api/classification/latest`, `/runs`, `/runs/{id}` |

Run không huấn luyện lại. Kết quả lần run lưu trong `model_runs.metrics`; lần train cũng ghi lịch sử. Classification có ba nhãn `low`, `medium`, `high`. Prediction/Classification dự đoán tháng kế tiếp bằng 12 tháng đầu vào liên tục. Các model kiểm tra tháng cuối và fingerprint dữ liệu. Clustering lưu StandardScaler, estimator K-Means, ánh xạ nhãn ổn định, tham số chọn cụm và fingerprint; dữ liệu thay đổi sẽ khiến run trả conflict thay vì fit lại.

Đường dẫn artifact mặc định dưới `BE/artifacts/`:

- Clustering: `electricity_demand_kmeans.joblib`, ghi đè bằng `CLUSTERING_MODEL_PATH`.
- Prediction: `electricity_demand_rf.joblib`, ghi đè bằng `PREDICTION_MODEL_PATH`.
- Classification: `electricity_demand_classifier.joblib`, ghi đè bằng `CLASSIFICATION_MODEL_PATH`.

Build artifact trong giai đoạn chuẩn bị demo bằng ba endpoint `/train`; ở demo chỉ gọi ba endpoint `/run`. Không xóa dữ liệu `electricity_consumption`. Để diễn tập xóa pattern, chỉ xóa bản ghi kết quả trong `model_runs` trên database test/demo riêng, sau đó gọi lại từng `/run` và các endpoint `/latest`/`/runs`.

## Dataset APIs

Admin có thể upload CSV bằng `POST /api/datasets/upload`, import bằng `POST /api/datasets/{id}/import`, hoặc gọi sync HTTPS cấu hình qua `DATASET_SYNC_URL` bằng `POST /api/datasets/sync`. Import dùng upsert theo khóa tự nhiên. Sync là thủ công; hiện chưa có scheduler tự động.

## Chạy local

Backend và Frontend hiện được chạy riêng bằng các lệnh sau (từ đúng thư mục):

```powershell
# Terminal Backend, tại BE
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal Frontend, tại FE
npm run dev
```

Mở `http://localhost:8000/docs` để xem OpenAPI. Nếu Frontend chạy ở origin khác, thêm origin chính xác vào `CORS_ORIGINS` và bật credentials ở request client.

## Kiểm thử

Các test API dùng database PostgreSQL riêng tên `electricity_analytics_test`; fixture từ chối mọi tên database khác và tái tạo schema trong database test. Không đặt `TEST_DATABASE_URL` trỏ vào database phát triển. Test model artifacts có thể chạy tách khỏi DB:

```powershell
# Tại BE
python -m pytest --noconftest -p no:cacheprovider tests/test_model_artifacts.py -q

# Bộ API đầy đủ, chỉ khi database riêng electricity_analytics_test sẵn sàng
$env:TEST_DATABASE_URL = "postgresql+psycopg://<user>:<password>@127.0.0.1:5433/electricity_analytics_test"
python -m pytest -p no:cacheprovider -q
```
