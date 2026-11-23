# Electricity Analytics Frontend

## Overview Dashboard

Trang `/` và ba trang phân tích sử dụng `GET /api/electricity/demand` từ FastAPI.
Nguồn dữ liệu là CSV đã xử lý trong dự án; cần chạy backend để tải biểu đồ.
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
Các mức dưới 21 TWh, từ 21 đến 27 TWh và trên 27 TWh là ngưỡng minh họa, chưa phải kết quả K-Means.
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
