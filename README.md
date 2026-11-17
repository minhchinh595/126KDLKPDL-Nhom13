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

### 6.1. Yêu cầu môi trường

- Python 3.13.11
- Node.js và npm
- Git
- PostgreSQL (khi triển khai Database)

### 6.2. Chạy Backend

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

### 6.3. Chạy Frontend

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
