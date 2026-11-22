import { AppLayout } from "@/components/layout/app-layout";
import { SectionPlaceholder } from "@/components/dashboard/section-placeholder";
import { Sparkles } from "lucide-react";

export default function PredictionPage() {
  return (
    <AppLayout>
      <SectionPlaceholder
        title="Dự đoán Nhu cầu Điện năng (Prediction)"
        subtitle="Mô hình Machine Learning và Time Series dự báo sản lượng điện tiêu thụ trong các kỳ tiếp theo."
        badge="Machine Learning"
        icon={Sparkles}
        targetObjective="Xây dựng mô hình Prediction để dự đoán nhu cầu điện năng tương lai với độ chính xác cao, hỗ trợ công tác quy hoạch năng lượng."
        nextSteps={[
          "Hiển thị đường dự báo tương lai cùng khoảng tin cậy (Confidence Interval)",
          "Bảng so sánh độ chính xác mô hình (MAE, RMSE, MAPE, R²)",
          "Form cho phép người dùng tùy chỉnh tham số dự báo (Số tháng dự đoán, kịch bản tăng trưởng)",
        ]}
      />
    </AppLayout>
  );
}
