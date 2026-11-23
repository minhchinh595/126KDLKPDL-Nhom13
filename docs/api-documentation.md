# API dữ liệu biểu đồ

## GET /api/electricity/demand

Trả về chuỗi nhu cầu điện Việt Nam từ CSV đã xử lý, không dùng hằng số dữ liệu trong frontend.
Endpoint trả toàn bộ lịch sử để frontend vẫn tính được MoM, YoY và biến trễ khi lọc thời gian.

```json
{
  "source": "data/processed/vietnam_electricity_demand.csv",
  "country": "Vietnam",
  "iso3": "VNM",
  "unit": "TWh",
  "total": 1,
  "start_month": "2019-01",
  "end_month": "2019-01",
  "records": [{ "month": "2019-01", "value": 17.87 }]
}
```

Ví dụ trên rút gọn còn một bản ghi. Dataset hiện có 93 tháng (2019-01 đến 2026-09).
Nguồn là dataset đi kèm dự án, không phải dữ liệu cập nhật thời gian thực; xuất xứ bên ngoài chưa được xác minh lại.

- HTTP 200: dữ liệu hợp lệ, bao gồm trường hợp `records: []`, `total: 0` và hai mốc thời gian `null`.
- HTTP 503: file không đọc được, thiếu cột hoặc có bản ghi không hợp lệ/trùng tháng.
- Chỉ nhận tổng nhu cầu (`iso3=VNM`, `metric=demand`, `fuel` trống), đơn vị TWh.
- Dữ liệu sắp xếp theo tháng; đọc lại CSV ở mỗi yêu cầu, trả `Cache-Control: no-store`.
- CORS cho `http://localhost:3000` và `http://127.0.0.1:3000`.

Backend mặc định tìm file theo vị trí mã nguồn, không phụ thuộc thư mục chạy lệnh.
Có thể đặt biến môi trường `ELECTRICITY_DATA_PATH` để sử dụng file CSV khác cùng cấu trúc.
Khi chạy container backend, mount thư mục dữ liệu vào `/data` (chỉ đọc) hoặc đặt biến này đến file được mount.

## Frontend

`NEXT_PUBLIC_API_URL` là địa chỉ backend, không chứa `/api` ở cuối, mặc định `http://localhost:8000`.
Ứng dụng gọi endpoint khi mở Dashboard hoặc trang phân tích và khi nhấn **Tải lại từ API**.
Frontend kiểm tra cấu trúc phản hồi, đơn vị, thời gian, số lượng và giá trị trước khi vẽ biểu đồ.
Không sử dụng dữ liệu mẫu thay thế khi lỗi. Có trạng thái tải, dữ liệu rỗng, lỗi và nút thử lại;
yêu cầu có thời hạn 15 giây và bị hủy khi rời trang.

Các trang sử dụng API: `/`, `/analysis/consumption`, `/analysis/trend`, `/analysis/correlation`.
KPI, biểu đồ, biến trễ và CSV sử dụng cùng dữ liệu trả về.
Phân bố mức tiêu thụ vẫn dùng ngưỡng cố định, chưa phải K-Means. Chưa có endpoint mô hình dự báo.

## Chạy và kiểm tra

Terminal backend, tại thư mục `BE`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal frontend, tại thư mục `FE`:

```powershell
npm run dev
```

Mở `http://localhost:8000/docs` để thử endpoint và `http://localhost:3000` để xem biểu đồ.
Nếu frontend chạy ở cổng khác 3000, cần bổ sung origin tương ứng trong CORS backend.

Kiểm tra tự động (chạy ở từng thư mục tương ứng):

```powershell
# BE: kiểm tra loader, handler, schema và cấu hình route/CORS, không dùng socket
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
# FE
node --test src/lib/analysis-data.test.mjs src/lib/demand-api.test.mjs
npm run build
```

Kiểm tra thủ công: API thành công, dừng backend để thấy lỗi, khởi động lại rồi thử lại;
đổi một giá trị trong CSV trên bản sao, đặt `ELECTRICITY_DATA_PATH` đến bản sao, tải lại API
và kiểm tra biểu đồ/KPI/CSV thay đổi. Không cần sửa hằng số frontend.
