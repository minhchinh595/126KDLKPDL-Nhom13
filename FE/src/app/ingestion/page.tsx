import { AppLayout } from "@/components/layout/app-layout";
import { SectionPlaceholder } from "@/components/dashboard/section-placeholder";
import { Database } from "lucide-react";

export default function IngestionPage() {
  return (
    <AppLayout>
      <SectionPlaceholder
        title="Thu thập & Quản lý Dữ liệu (Data Ingestion)"
        subtitle="Quy trình nạp, làm sạch và tích hợp dữ liệu tiêu thụ điện năng từ Ember vào hệ thống."
        badge="Data Pipeline"
        icon={Database}
        targetObjective="Thu thập và tích hợp dữ liệu tiêu thụ điện năng từ các nguồn dữ liệu; Xây dựng quy trình Data Ingestion để cập nhật dữ liệu tự động."
        nextSteps={[
          "Kết nối API nạp dữ liệu từ backend FastAPI (app/ingestion/reader.py, cleaner.py)",
          "Hiển thị bảng chi tiết các đợt nạp dữ liệu và kiểm tra tính toàn vẹn (Missing values, Outliers)",
          "Hỗ trợ tải lên file CSV/Excel mới và cập nhật vào kho dữ liệu",
        ]}
      />
    </AppLayout>
  );
}
