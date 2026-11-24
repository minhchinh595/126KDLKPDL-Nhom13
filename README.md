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
- PostgreSQL 16

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
- PostgreSQL 16 (được cung cấp qua Docker Compose hoặc cài đặt riêng)

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

## 7. Chạy toàn bộ hệ thống bằng Docker Compose

Docker Compose khởi chạy PostgreSQL, Backend API Gateway, năm backend service độc lập và Frontend. Chỉ Gateway kết nối PostgreSQL; Gateway gọi các service nội bộ qua DNS của Docker. Cấu hình hiện tại không tự chạy migration hoặc import dataset khi khởi động.

### 7.1. Cổng truy cập

| Thành phần | Cổng trong container | Cổng/địa chỉ từ máy host |
| --- | ---: | --- |
| PostgreSQL | 5432 | `127.0.0.1:5433` |
| Gateway | 8000 | `http://localhost:8001` |
| Frontend | 3000 | `http://localhost:3000` |
| Analysis | 8101 | Chỉ nội bộ Docker: `analysis:8101` |
| Clustering | 8102 | Chỉ nội bộ Docker: `clustering:8102` |
| Prediction | 8103 | Chỉ nội bộ Docker: `prediction:8103` |
| Classification | 8104 | Chỉ nội bộ Docker: `classification:8104` |
| Ingestion | 8105 | Chỉ nội bộ Docker: `ingestion:8105` |

Các cổng 8101–8105 không được publish ra máy host. Gateway nhận request từ host qua cổng 8001 và lắng nghe cổng 8000 bên trong container.

### 7.2. Cấu hình và khởi chạy Docker Compose

Từ thư mục gốc, tạo `.env` từ file mẫu:

```powershell
Copy-Item .env.example .env
```

Trong `.env`, đặt `POSTGRES_USER`, `POSTGRES_PASSWORD`, `JWT_SECRET_KEY` và năm service secret riêng biệt: `ANALYSIS_SERVICE_SECRET`, `CLUSTERING_SERVICE_SECRET`, `PREDICTION_SERVICE_SECRET`, `CLASSIFICATION_SERVICE_SECRET`, `INGESTION_SERVICE_SECRET`. Tạo JWT secret và từng service secret bằng giá trị ngẫu nhiên riêng; mỗi secret cần tối thiểu 32 bytes. Có thể chạy lệnh sau sáu lần và dùng mỗi kết quả cho đúng một biến:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Không dùng chung một secret cho nhiều service. Đặt `NEXT_PUBLIC_API_URL=http://localhost:8001` để Frontend gọi Gateway qua cổng host đã publish. Dùng mật khẩu PostgreSQL an toàn với URL vì Compose tạo `DATABASE_URL` nội bộ cho Gateway từ các biến PostgreSQL.

`APP_ENV=development` dành cho môi trường local dùng HTTP. Khi triển khai qua HTTPS, đặt `APP_ENV=production`. Compose chuyển giá trị này vào Gateway; giá trị mặc định là `development`.

Nếu dùng database mới, trước khi sử dụng đầy đủ API cần áp dụng migration và import dataset theo hướng dẫn tại mục 6.1. Thực hiện các bước đó theo quy trình triển khai; Compose không tự động chạy migration hoặc import dữ liệu khi startup.

Kiểm tra cấu hình và khởi chạy:

```powershell
docker compose config --services
docker compose config --quiet
docker compose up -d --build
```

Compose build một Backend image dùng chung cho Gateway và năm service nội bộ. PostgreSQL tiếp tục dùng container `electricity-analytics-postgres` và volume persistent `electricity_analytics_postgres_data`. Thư mục `BE/uploads` được mount cho file upload; `BE/artifacts` được chia sẻ với các service ML; thư mục `data` được mount chỉ đọc.

### 7.3. Health, log và dừng hệ thống

- Gateway health: `http://localhost:8001/api/health`.
- Frontend: `http://localhost:3000`.
- PostgreSQL từ máy host: `127.0.0.1:5433`.
- Health endpoint của năm service nội bộ được Compose kiểm tra, nhưng không publish cổng ra host.

Xem log bằng `docker compose logs -f gateway`; thay `gateway` bằng `frontend`, `postgres`, `analysis`, `clustering`, `prediction`, `classification` hoặc `ingestion` để xem service tương ứng.

Dừng các service mà vẫn giữ dữ liệu persistent:

```powershell
docker compose stop
```

Không dùng `docker compose down -v`: tùy cấu hình volume, lệnh này có thể xóa volume và dữ liệu PostgreSQL persistent.

## 8. Phát triển local không dùng Docker Compose

Các hướng dẫn mục này dành cho việc chạy từng process local, tách biệt với cách khởi chạy toàn hệ thống bằng Docker Compose. Đặt URL service trong `.env` ở `http://127.0.0.1:8101` đến `http://127.0.0.1:8105`, đặt các secret tương ứng và dùng `DATABASE_URL` trỏ tới PostgreSQL trên host, thường là cổng `5433`. Dùng `APP_ENV=development` cho HTTP local.

Chạy Gateway và mỗi service trong terminal riêng, từ thư mục `BE`:

```powershell
cd BE
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --env-file ..\.env
python -m uvicorn service_apps.analysis.main:app --reload --host 127.0.0.1 --port 8101 --env-file ..\.env
python -m uvicorn service_apps.clustering.main:app --reload --host 127.0.0.1 --port 8102 --env-file ..\.env
python -m uvicorn service_apps.prediction.main:app --reload --host 127.0.0.1 --port 8103 --env-file ..\.env
python -m uvicorn service_apps.classification.main:app --reload --host 127.0.0.1 --port 8104 --env-file ..\.env
python -m uvicorn service_apps.ingestion.main:app --reload --host 127.0.0.1 --port 8105 --env-file ..\.env
```

Mỗi lệnh Uvicorn trên chạy trong một terminal riêng. Frontend local chạy tại `http://localhost:3000`; đặt `NEXT_PUBLIC_API_URL=http://localhost:8000` trong `FE/.env.local` rồi chạy `npm run dev` từ `FE`. Cổng Gateway local là 8000; cổng host của Gateway trong Docker Compose là 8001.
