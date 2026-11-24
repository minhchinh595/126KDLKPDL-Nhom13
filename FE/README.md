# Electricity Analytics Frontend

## Đăng nhập để tải dữ liệu

Backend mới yêu cầu cookie đăng nhập cho API tiêu thụ. Khi nhận HTTP 401, Dashboard và các trang
phân tích hiển thị form đăng nhập: nhập email/mật khẩu tài khoản Admin hoặc Analyst đã tạo trên backend.
Đăng nhập thành công sẽ tải lại biểu đồ; không cần đăng nhập qua Swagger.

Yêu cầu đăng nhập và dữ liệu đều dùng `credentials: "include"`, cookie do backend giữ ở chế độ HttpOnly.
Frontend không lưu mật khẩu hoặc JWT vào localStorage. Cookie `SameSite=Lax` cần frontend và API cùng site:
khi chạy local, client đồng bộ `localhost`/`127.0.0.1` với hostname trên thanh địa chỉ, giữ nguyên cổng API.
Địa chỉ API từ xa không bị đổi. Các origin frontend vẫn phải được khai báo trong CORS backend.

Client tải đủ các trang của API `/api/electricity/demand` trước khi tính KPI/biểu đồ để không mất lịch sử
khi dataset vượt giới hạn một trang. HTTP 403 hiển thị lỗi quyền truy cập; HTTP 401 hiển thị form đăng nhập lại.

## Overview Dashboard

### API đang được sử dụng

| Màn hình | API |
|---|---|
| Toàn bộ chuỗi dữ liệu, bảng, so sánh cùng kỳ | `/api/electricity/demand` (đọc đủ phân trang) |
| Thống kê toàn kho trên Dashboard | `/api/dashboard/overview` |
| KPI theo khoảng lọc trên Dashboard và Consumption | `/api/analysis/summary` |
| Đường trung bình trượt trên Dashboard và Trend | `/api/analysis/trend` |
| Thống kê theo tháng trên Dashboard và Trend | `/api/analysis/seasonality` |
| Hệ số và ma trận Pearson trên Correlation | `/api/analysis/correlation` |
| Histogram trên Dashboard và Consumption | `/api/analysis/distribution` |

Các API phân tích nhận `start_month`/`end_month`; Trend thêm `window_months`, Distribution thêm `bins`.
Khi đổi bộ lọc, request cũ được hủy và kết quả cũ bị ẩn cho tới khi request mới hoàn tất.
HTTP 401 yêu cầu đăng nhập lại; HTTP 503 hiển thị lỗi dịch vụ và nút thử lại, không tính thay bằng dữ liệu local.

Chạy Analysis Service tại cổng 8101 bên cạnh Gateway cổng 8000. Hai tiến trình phải dùng cùng
`ANALYSIS_SERVICE_SECRET` trong `.env` gốc. Tại thư mục `BE`, sau khi kích hoạt `.venv`:

```powershell
python -m uvicorn service_apps.analysis.main:app --host 127.0.0.1 --port 8101 --env-file ..\.env
```

Backend hiện trả Pearson cho ba biến `demand`, `previous_month`, `previous_year`; frontend không hiển thị
Spearman như kết quả API. Điểm scatter được ghép từ dữ liệu nguồn trong đúng khoảng lọc vì endpoint chỉ
trả ma trận và số cặp. Các phép gộp tháng/quý/năm, tổng và so sánh cùng kỳ là phép trình bày từ chuỗi API.
Dashboard Overview là thống kê toàn kho, không nhận bộ lọc thời gian; phần này được ghi nhãn riêng.

Kiểm tra phần kết nối mới:

```powershell
node --test src/lib/analysis-data.test.mjs src/lib/demand-api.test.mjs src/lib/analytics-api.test.mjs
```

Trang `/` và ba trang phân tích sử dụng `GET /api/electricity/demand` từ FastAPI.
Nguồn dữ liệu là PostgreSQL đã import dataset của dự án; cần chạy Gateway và Analysis Service để tải đầy đủ biểu đồ.
Cấu hình `NEXT_PUBLIC_API_URL=http://localhost:8000` trong `.env.local`.
Xem [hướng dẫn API và chạy hai ứng dụng](../docs/api-documentation.md).

- Bộ lọc từ tháng/đến tháng, 12 tháng gần nhất, năm dữ liệu mới nhất và toàn bộ.
- KPI được tính lại theo khoảng lọc: tháng cuối kỳ, tổng, trung bình và tháng cao nhất.
- Biểu đồ lịch sử có so sánh cùng kỳ, thống kê theo tháng trong năm và phân bố mức tiêu thụ.
- Bảng hỗ trợ tìm tháng, lọc mức tiêu thụ, sắp xếp, phân trang và xuất CSV toàn bộ kết quả lọc.
- Bộ lọc riêng của bảng không thay đổi KPI hay biểu đồ; nút đặt lại Dashboard khôi phục tất cả bộ lọc.
- Liên kết đến Consumption Analysis, Trend & Seasonality và Correlation.
- Có trạng thái tải, khoảng lọc không hợp lệ, không có kết quả và trang xử lý lỗi.

MoM/YoY tra đúng tháng lịch sử trước khi lọc; giá trị thiếu hoặc mẫu số bằng 0 được hiển thị là dấu `—`.
Nhãn mức tiêu thụ trong bảng dùng các ngưỡng cố định 21/27 TWh. Biểu đồ phân bố dùng histogram từ API, chưa phải K-Means.
Chưa có API mô hình dự báo, vì vậy Dashboard không hiển thị chuỗi dự báo mẫu.
Có trạng thái tải API, lỗi/thử lại, dữ liệu rỗng và nút tải lại dữ liệu; không tự chuyển sang dữ liệu mẫu.

Kiểm tra trước khi bàn giao:

```bash
node --test src/lib/analysis-data.test.mjs src/lib/demand-api.test.mjs
npm run build
```

Chạy `npm run dev`, mở `http://localhost:3000` để kiểm tra giao diện. Thử đổi khoảng tháng,
bật/tắt so sánh cùng kỳ, nhập khoảng không có dữ liệu, lọc bảng, chuyển trang và tải CSV.

---

This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
