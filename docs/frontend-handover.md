# Rà soát và bàn giao Frontend — 24/11/2026

## Đối chiếu với Backend

- Docker Compose ánh xạ Gateway ra `localhost:8001`; frontend trước đó còn dùng cổng 8000. Đã sửa cấu hình mặc định, liên kết Swagger, health check và `.env.local` frontend sang 8001.
- Backend vẫn chạy nội bộ cổng 8000 trong container; đây không phải lỗi ánh xạ. `BE/README.md` còn các lệnh dev local cổng 8000, không nên dùng chúng làm cấu hình frontend cho bản Compose 8001.
- Đã đọc hợp đồng OpenAPI sinh từ `app.openapi()` của mã BE hiện tại vì kết nối HTTP tới Swagger bị môi trường kiểm tra chặn. Các endpoint và schema được dùng theo hợp đồng này, không tạo API mới.
- Gateway yêu cầu cookie và role thực từ `/api/auth/me`. Frontend trước đó mới có form khi gặp lỗi dữ liệu, chưa có phiên chung và phân quyền cho các trang mô hình/dataset.
- Clustering chỉ nhận `max_k` từ 2 đến 8 ở train; Gateway tự chọn K. Prediction/Classification không nhận horizon/thuật toán tùy ý. Giao diện không thêm tham số không được API hỗ trợ.
- `ModelRun.metrics` thay đổi theo model/stage; per-class classification là object theo nhãn, không phải array. Giao diện đã xử lý theo cấu trúc thực.
- Không sửa mã Backend, migration, schema, Docker Compose hoặc volume. Không chạy bộ test BE có fixture tạo/xóa bảng.

## Phần frontend đã triển khai

| Phần | Nội dung |
|---|---|
| Authentication | Phiên chung từ `/auth/me`, đăng nhập cookie HttpOnly, đăng xuất, xử lý hết phiên, kiểm tra lại khi cửa sổ được focus |
| Quyền | Admin có thao tác train/run/upload/import/sync/user management; Analyst xem dữ liệu/kết quả/lịch sử; HTTP 403 được hiển thị |
| Dashboard | API Overview, demand phân trang, analysis và dự báo mới nhất thật; không còn forecast mẫu |
| Analysis | Summary, Trend, Seasonality, Correlation Pearson, Distribution; bộ lọc và CSV; không giả lập Spearman |
| Clustering | Train với max_k hợp lệ, Run độc lập, silhouette, chọn K, thống kê và phân công cụm, lịch sử/chi tiết |
| Prediction | Train/Run, forecast một tháng theo contract, biểu đồ dữ liệu thật + dự báo, holdout metrics, lịch sử/chi tiết |
| Classification | Trang mới, Train/Run, mức dự báo, xác suất, accuracy/per-class/confusion matrix, lịch sử/chi tiết |
| Ingestion | Upload multipart CSV, validation API, import riêng, tìm kiếm/phân trang, lịch sử, sync khi backend đã cấu hình; cập nhật nguồn demand sau import |
| Settings | Hồ sơ/role hiện tại, readiness từ Gateway, Admin tạo Analyst/Admin và sửa role/trạng thái; không hiển thị secret |
| Trạng thái/UI | Loading, lỗi/thử lại, empty/404, 401/403/409/413/422/503, khóa nút khi ghi, không tự retry train/import, bảng cuộn ngang, header mobile |

## Kiểm chứng đã thực hiện

- 65 tests Node cho tính toán, API adapters, cookie, phân trang, hợp đồng Analysis Service, quyền và request Gateway: đạt, không có tests bị bỏ qua trong lượt chạy cuối.
- TypeScript và toàn bộ ESLint đã đạt ở các vòng kiểm tra.
- Production build đã hoàn tất thành công một lần cho 14 route. Các lượt build cuối đều compile và kiểm tra TypeScript thành công nhưng bị EPERM khi prerender/ghi thư mục đầu ra, kể cả khi thử thư mục build riêng. Vì vậy chưa đánh dấu bản build cuối là đạt. Các cấu hình frontend tạm dùng để kiểm tra đã được khôi phục; không thay cấu hình Backend.
- Kiểm tra HTTP thật: **blocked ngay bước health**, WinError 10013 / EACCES khi mở socket localhost. Báo cáo local `FE/test-results/gateway-e2e.json` ghi `status: blocked`, chưa có check thực tế nào được tính là passed.
- Không xác nhận lại các con số 103 BE tests/22 GET trong bản bàn giao, vì chưa truy cập được Gateway thật từ môi trường này.
- Cài Playwright bị chặn DNS tới npm (`ENOTFOUND registry.npmjs.org`). Bộ kiểm thử trình duyệt đã viết, kiểm tra cú pháp; **chưa chạy thực tế**.

## Chưa được coi là nghiệm thu

1. Chưa tạo tài khoản Analyst thật trong lần làm việc này: chưa có phiên Admin có thể truy cập Gateway. Giao diện Settings và script kiểm thử đều tạo qua `/api/users`, không chèn SQL và không reset mật khẩu tài khoản đã tồn tại.
2. Chưa có kết quả E2E thật cho đăng nhập Admin/Analyst, import, train/run và lưu lịch sử xuyên Gateway–Microservices–PostgreSQL.
3. Chưa xác nhận trực tiếp layout desktop/mobile trên trình duyệt thật. Không dùng tests fixture thay cho kết luận này.

## Chạy nghiệm thu trên máy có Gateway đang hoạt động

Từ thư mục FE, giữ frontend và Docker backend chạy sẵn:

```powershell
# HTTP tích hợp; hỏi mật khẩu ẩn ở terminal, không lưu credentials ra file
..\BE\.venv\Scripts\python.exe scripts/gateway-e2e.py --exercise-writes

# Chuẩn bị kiểm thử trình duyệt (cần kết nối npm)
npm install --save-dev @playwright/test
npx playwright install chromium
..\BE\.venv\Scripts\python.exe scripts/browser-e2e.py --exercise-writes
```

Chế độ `--exercise-writes` tạo Analyst nếu chưa có, upload/import CSV thật của dự án, huấn luyện và chạy ba mô hình qua Gateway. Nó tạo các bản ghi/lịch sử và artifact theo chức năng công khai; không xóa database/volume. Dùng môi trường kiểm thử đã được nhóm chỉ định.

Report local trong `FE/test-results/` đã được Git bỏ qua, không chứa mật khẩu/cookie. Suite trình duyệt tắt trace/video; không dùng mock route. Nếu kiểm tra thất bại, xử lý theo endpoint/status thực tế trước khi ký nghiệm thu.

## Bổ sung task Data Management / Model Management

- Kết nối Clustering, Prediction, Classification đã có trong code trước đợt này: train/run/latest/history/detail, cookie Gateway, phân quyền và kết quả thực từ API.
- Bổ sung `/models`: lịch sử tổng hợp, lọc loại mô hình/trạng thái/thứ tự/phân trang, xem chi tiết và xuất CSV trang hiện tại; liên kết tới ba trang mô hình.
- Data Management dùng `/ingestion`, thêm alias `/data-management`, bổ sung GET chi tiết dataset với file, nguồn, mô tả, số dòng, khoảng thời gian và thời điểm tạo/cập nhật. Giữ upload/import/history/sync hiện có.
- Bổ sung điều hướng và kiểm thử tham số API mô hình; HTTP/browser suites mở rộng cho dataset detail và lịch sử tổng hợp.
- Kiểm tra hiện tại: **74/74 Node tests passed**, TypeScript và ESLint passed; browser suite và Python script qua kiểm tra cú pháp. Không thay đổi mã BE.
- Health từ môi trường công cụ vẫn bị chặn quyền socket Windows; chưa thể xác nhận E2E thực tế hoặc tạo tài khoản Analyst trong lượt này. Log health thành công do người dùng cung cấp xác nhận Gateway/DB trên terminal của người dùng, không thay thế kiểm thử toàn bộ luồng mới.
- Không tạo API sửa/xóa dataset/model vì Backend chưa có các contract này.
- Build sau bổ sung 16 routes: compile và TypeScript thành công, nhưng prerender bị Windows EPERM khi tạo `.next/server/app/clustering.segments/clustering`; chưa xác nhận production build cuối cùng đạt.

## Cập nhật giao diện theo thứ tự ưu tiên

1. Giao diện chung: font hệ thống hỗ trợ tiếng Việt, nền xám sáng, card trắng, màu cam nhấn; sidebar nhóm tổng quan/phân tích/mô hình/hệ thống, tự đóng khi chọn trang trên mobile; thêm liên kết bỏ qua điều hướng bằng bàn phím.
2. Dashboard: tiêu đề đồng bộ, thẻ KPI dễ đọc, số liệu dùng tabular numerals, khoảng cách và bảng dữ liệu thống nhất.
3. Data Management: tiêu đề riêng, badge trạng thái dataset/import, bảng với header cố định, vùng cuộn ngang có thể focus, form cao 40px.
4. Model Management: tiêu đề, badge trạng thái, bảng lịch sử và các trang mô hình dùng cùng bộ component.
5. Analysis, Settings, Login: đồng bộ heading, panel, form, loading/error/empty states; biểu đồ cao 256px trên mobile/320px từ breakpoint sm; hỗ trợ reduced motion.

Áp dụng bố cục dashboard shadcn bằng các component hiện có; không nhập authentication hoặc dependency của template. Mã API và schema BE không đổi. Nguồn CSS là `FE/src/app/globals.source.css`; `npm run dev` hoặc `npm run build:css` tạo lại `globals.css`.

Kiểm tra: 74 tests, TypeScript, ESLint và CSS compilation đạt. Production build compile/TypeScript đạt nhưng bị Windows EPERM khi prerender `/data-management`; chưa kiểm tra trực quan desktop/mobile bằng trình duyệt trong môi trường công cụ này.
