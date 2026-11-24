# Electricity Consumption Analytics — Frontend

Frontend chỉ gọi API Gateway `http://localhost:8001`. Không gọi service 8101–8105, không truy cập PostgreSQL và không dùng dữ liệu mẫu để thay thế API lỗi.

## Chạy frontend

```powershell
cd FE
npm install
```

Cấu hình `FE/.env.local` (không commit):

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8001
```

```powershell
npm run dev
```

Mở `http://localhost:3000`. Đăng nhập bằng tài khoản Admin hoặc Analyst đã có trên Gateway.
Cookie HttpOnly được gửi bằng `credentials: "include"`; không lưu JWT/mật khẩu trong localStorage.
Khi chạy local, hostname API theo `localhost`/`127.0.0.1` của trình duyệt để cookie cùng site; cổng giữ nguyên 8001.

## Màn hình và hợp đồng API

| Màn hình | API Gateway | Quyền |
|---|---|---|
| Login, đăng xuất, phiên | `/api/auth/login`, `/logout`, `/me` | Tài khoản đang hoạt động |
| Dashboard | `/api/dashboard/overview`, `/api/electricity/demand`, `/api/prediction/latest` | Admin/Analyst |
| Consumption / histogram | `/api/analysis/summary`, `/distribution`, dữ liệu demand phân trang | Admin/Analyst |
| Trend / Seasonality | `/api/analysis/trend`, `/seasonality` | Admin/Analyst |
| Correlation | `/api/analysis/correlation` | Admin/Analyst |
| Clustering | `/api/clustering/train`, `/run`, `/latest`, `/runs`, `/runs/{id}` | Train/run: Admin; đọc: cả hai |
| Prediction | `/api/prediction/train`, `/run`, `/latest`, `/runs`, `/runs/{id}` | Train/run: Admin; đọc: cả hai |
| Classification | `/api/classification/train`, `/run`, `/latest`, `/runs`, `/runs/{id}` | Train/run: Admin; đọc: cả hai |
| Ingestion | `/api/datasets`, `/upload`, `/{id}/import`, `/{id}/history`, `/sync`, `/sync/status` | Upload/import/sync: Admin; đọc: cả hai |
| Settings | `/api/health/ready`, phiên hiện tại, `/api/users`, `/{id}`, `/{id}/status` | Quản lý tài khoản: Admin |

Backend quyết định quyền cuối cùng; frontend ẩn thao tác ghi với Analyst và xử lý HTTP 403.
Khi HTTP 401 hoặc hết phiên, giao diện quay về đăng nhập và bỏ nội dung đã bảo vệ.
Settings có form tạo Analyst; không có tài khoản hay mật khẩu mặc định trong code.

Phân tích gửi `start_month`, `end_month`, Trend thêm `window_months`, Distribution thêm `bins`.
Dashboard Overview là thống kê toàn kho, có nhãn riêng; các thẻ/biểu đồ theo khoảng lọc dùng API Analysis.
Correlation hiển thị Pearson do API cung cấp, không giả lập Spearman. Scatter ghép từ chuỗi API trong cùng khoảng lọc.
Histogram từ API khác với nhãn ngưỡng 21/27 TWh trong bảng; không gán nhãn K-Means cho histogram.
Mô hình có hai nút riêng: huấn luyện tạo artifact, chạy chỉ dùng artifact hiện có. Không tự train khi mở trang hoặc khi API trả lỗi.
Gateway chỉ hỗ trợ `max_k` (2–8) cho Clustering, không nhận lựa chọn K cố định hay horizon tùy ý; UI tuân thủ đúng contract.

## Dữ liệu và trạng thái

Upload hỗ trợ CSV qua multipart với `file`, `name`, `source`, `description` tùy chọn. Không đặt Content-Type thủ công cho multipart.
File được Gateway/Ingestion Service validate; import là thao tác riêng. Lịch sử có số dòng thêm/cập nhật/bỏ qua/lỗi.
CSV nguồn của dự án ở `data/processed/vietnam_electricity_demand.csv` có thể dùng để kiểm tra.
Không tự import, train, sync hoặc tạo tài khoản khi mở trang. Các thao tác ghi có nút riêng, khóa khi đang xử lý và không tự retry.
Nếu request ghi hết thời gian chờ, tải lại lịch sử trước khi thao tác lần nữa vì server có thể vẫn hoàn tất.

Có loading, lỗi/thử lại, empty, phân trang, tìm kiếm, trạng thái quyền; bảng cuộn ngang trên màn hình hẹp.
Settings chỉ hiển thị thông tin Gateway/DB mà API cung cấp; không cho sửa secret hoặc cấu hình Docker từ trình duyệt.

## Kiểm tra cục bộ

```powershell
npm test
npm run lint
npm run build
```

Tests dùng fixture chỉ trong kiểm thử; không có mock fallback trong các luồng ứng dụng.
Các kiểm tra contract có thể đọc schema/thuật toán BE trực tiếp mà không mở kết nối DB.
Không chạy bộ test backend tạo/xóa bảng trong quá trình bàn giao frontend.

## Kiểm thử HTTP thật qua Gateway

Gateway/Docker Compose và database cần đang chạy sẵn theo cấu hình đội backend. Script không khởi động/sửa container, volume hay schema.
Tại thư mục FE:

```powershell
..\BE\.venv\Scripts\python.exe scripts/gateway-e2e.py --exercise-writes
```

Script hỏi email/mật khẩu Admin và Analyst cục bộ (ẩn mật khẩu), tạo Analyst qua API nếu chưa có;
upload/import CSV thật của dự án, train/run ba mô hình, kiểm tra kết quả/lịch sử và quyền 403 của Analyst.
Chế độ này ghi tài khoản/dataset/lịch sử/model artifacts qua API; không xóa dữ liệu hoặc volume.
Đối với Analyst đã tồn tại phải cung cấp đúng mật khẩu, script không tự đổi/reset mật khẩu.
Bỏ `--exercise-writes` nếu chỉ kiểm tra các luồng đọc và đăng nhập Admin.
Report ở `FE/test-results/gateway-e2e.json`, không chứa mật khẩu/cookie, được Git bỏ qua.

## Kiểm thử trình duyệt thật

Cài dependency kiểm thử trên máy có kết nối npm:

```powershell
npm install --save-dev @playwright/test
npx playwright install chromium
```

Giữ frontend và Gateway chạy. Tại FE:

```powershell
..\BE\.venv\Scripts\python.exe scripts/browser-e2e.py --exercise-writes
```

Suite không dùng route mock: đăng nhập, Dashboard, biểu đồ/bộ lọc/CSV, tạo Analyst qua Settings,
upload/import/validation CSV, train/run/history ba mô hình, đăng xuất, kiểm tra Analyst và viewport mobile.
Trace/video tắt để không lưu request đăng nhập; kết quả và ảnh lỗi chỉ ở `FE/test-results/` (ignored).
Không coi tests fixture/schema là thay thế cho nghiệm thu E2E trên hệ thống đang chạy.

## Data Management và Model Management

- **Data Management:** `/ingestion` (hoặc `/data-management`, tự chuyển hướng). Danh sách dataset, tìm kiếm/phân trang, chi tiết file/nguồn/mô tả/số dòng/khoảng thời gian; upload CSV, import, lịch sử và đồng bộ theo quyền Admin/Analyst.
- **Model Management:** `/models`. Lịch sử chung từ `GET /api/model-runs`, lọc `model_type`, `status`, `order`, `page`, `page_size`; xem chi tiết từ `GET /api/model-runs/{run_id}`, xuất CSV của trang hiện tại. Có liên kết đến ba trang mô hình.
- **Clustering / Prediction / Classification:** `/clustering`, `/prediction`, `/classification`. Các trang dùng Gateway `/api/{kind}/train`, `/run`, `/latest`, `/runs`, `/runs/{id}`. Chỉ Clustering training gửi `max_k` (2–8); Prediction/Classification dùng cấu hình hiện có của Backend. Admin huấn luyện/chạy, Analyst chỉ xem.
- Contract Backend hiện không có API sửa/xóa dataset hoặc xóa model artifact, nên giao diện không cung cấp các thao tác đó.

Kiểm tra nhanh: đăng nhập Admin, mở Data Management và chọn **Chi tiết & lịch sử**; mở từng mô hình, huấn luyện rồi chạy; mở Model Management để lọc và xem lượt vừa tạo. Đăng nhập Analyst và kiểm tra quyền xem, không có nút ghi dữ liệu/chạy mô hình. Scripts HTTP và browser đã có kiểm tra chi tiết dataset, lịch sử tổng hợp và quyền Analyst.
