# Electricity Consumption Analytics

**Hệ thống phân tích mức tiêu thụ điện năng nhằm nhận diện quy luật sử dụng và dự đoán nhu cầu điện.**

## 1. Giới thiệu dự án

Dự án xây dựng hệ thống phân tích dữ liệu tiêu thụ điện năng nhằm khám phá các quy luật sử dụng năng lượng, phân nhóm đặc điểm tiêu thụ và dự đoán nhu cầu điện trong tương lai.

Hệ thống sử dụng các kỹ thuật thuộc lĩnh vực Data Warehouse và Data Mining để thu thập, xử lý, phân tích và trực quan hóa dữ liệu điện năng.

## 2. Mục tiêu dự án

- Thu thập và tích hợp dữ liệu tiêu thụ điện năng từ các nguồn dữ liệu.
- Xây dựng quy trình Data Ingestion để cập nhật dữ liệu.
- Phân tích xu hướng và quy luật tiêu thụ điện.
- Sử dụng Clustering để phân nhóm các đặc điểm tiêu thụ điện.
- Xây dựng mô hình Prediction để dự đoán nhu cầu điện.
- Trực quan hóa kết quả phân tích trên giao diện Dashboard.

## 3. Công nghệ sử dụng

### Frontend
- Next.js
- React
- TypeScript
- Tailwind CSS
- shadcn/ui
- Recharts
- Lucide React

### Backend
- Python 3.13.11
- FastAPI
- Uvicorn

### Data Analysis & Machine Learning
- Pandas
- NumPy
- Scikit-learn
- Matplotlib

### Database
- PostgreSQL (dự kiến)

## 4. Kiến trúc hệ thống

Hệ thống được tổ chức thành các thành phần chính:

1. **Data Source:** Nguồn cung cấp dữ liệu tiêu thụ điện năng.
2. **Data Ingestion:** Thu thập và cập nhật dữ liệu.
3. **Database:** Lưu trữ dữ liệu.
4. **Database API:** Cung cấp API để truy xuất dữ liệu.
5. **Data Analysis:** Phân tích dữ liệu tiêu thụ điện.
6. **Clustering:** Phân nhóm dữ liệu.
7. **Prediction:** Dự đoán nhu cầu điện.
8. **Frontend:** Hiển thị Dashboard và kết quả phân tích.

## 5. Cấu trúc thư mục

```text
DOAN-KHODULIEU/
│
├── BE/                     # Backend - FastAPI
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── ingestion/
│   │   ├── analysis/
│   │   ├── clustering/
│   │   └── prediction/
│   ├── tests/
│   └── requirements.txt
│
├── FE/                     # Frontend - Next.js
│   ├── public/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   │   ├── ui/
│   │   │   ├── layout/
│   │   │   ├── dashboard/
│   │   │   └── charts/
│   │   ├── lib/
│   │   └── types/
│   └── package.json
│
├── data/                   # Dataset
│
├── docs/                   # Project documentation
│
├── .gitignore
└── README.md
```

## 6. Hướng dẫn cài đặt và chạy dự án

### 6.1. PostgreSQL và migrations

Từ thư mục gốc, tạo cấu hình cục bộ từ mẫu và thay mật khẩu bằng một mật khẩu riêng:

```powershell
Copy-Item .env.example .env
```

Khởi động PostgreSQL riêng cho dự án (cổng máy chủ `5433`, volume riêng):

```powershell
docker compose up -d postgres
```

Trong `BE`, cài dependencies, áp dụng schema và xem trạng thái migration:

```powershell
cd BE
..\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
alembic upgrade head
alembic current
```

Hoặc sau khi kích hoạt virtualenv tại `BE`, dùng các lệnh `alembic upgrade head`,
`alembic downgrade -1`, `alembic current`, `alembic history` và
`alembic revision --autogenerate -m "describe schema change"`. Migration được lưu
trong `BE/alembic/versions`; không sửa migration đã áp dụng.

Import dataset đã xử lý (chỉ chạy khi migration đã hoàn tất):

```powershell
python .\scripts\import_electricity_data.py
```

Script kiểm tra schema và từng dòng trước khi ghi, tạo/cập nhật metadata dataset,
bỏ qua bản ghi trùng và có thể chạy lại. CSV gốc và CSV đã xử lý được giữ nguyên.
Xem dữ liệu bằng pgAdmin với host `127.0.0.1`, port `5433`, database
`electricity_analytics_db`, và thông tin đăng nhập trong `.env`; hoặc dùng:

```powershell
docker compose exec postgres psql -U electricity_app -d electricity_analytics_db -c "SELECT COUNT(*) FROM electricity_consumption;"
```

Để kiểm tra migration, dùng `alembic history` và `alembic current` từ thư mục `BE`.
Kết nối backend cũng đọc `DATABASE_URL` từ biến môi trường hoặc `.env` ở thư mục gốc.

### 6.2. Yêu cầu môi trường

- Python 3.13.11
- Node.js và npm
- Git
- PostgreSQL (khi triển khai Database)

### 6.3. Chạy Backend

Di chuyển vào thư mục Backend:

```bash
cd BE
```

Tạo môi trường ảo:

```bash
python -m venv venv
```

Kích hoạt môi trường ảo trên Windows:

```powershell
.\venv\Scripts\Activate.ps1
```

Cài đặt thư viện:

```bash
pip install -r requirements.txt
```

Khởi chạy Backend:

```bash
uvicorn app.main:app --reload
```

Backend chạy tại:

```text
http://127.0.0.1:8000
```

API Documentation:

```text
http://127.0.0.1:8000/docs
```

### 6.4. Chạy Frontend

Mở Terminal mới và di chuyển vào thư mục Frontend:

```bash
cd FE
```

Cài đặt dependencies:

```bash
npm install
```

Khởi chạy Frontend:

```bash
npm run dev
```

Frontend chạy tại:

```text
http://localhost:3000
```

*Project developed for the Data Warehouse and Data Mining course.*
