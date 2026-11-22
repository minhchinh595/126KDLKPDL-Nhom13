import { AppLayout } from "@/components/layout/app-layout";
import { SectionPlaceholder } from "@/components/dashboard/section-placeholder";
import { Shapes } from "lucide-react";

export default function ClusteringPage() {
  return (
    <AppLayout>
      <SectionPlaceholder
        title="Phân cụm Đặc trưng Tiêu thụ (Clustering)"
        subtitle="Ứng dụng kỹ thuật khai phá dữ liệu (K-Means, DBSCAN) để phân nhóm các mẫu hình tiêu thụ điện."
        badge="Data Mining"
        icon={Shapes}
        targetObjective="Sử dụng Clustering để phân nhóm các đặc điểm tiêu thụ điện năng, hỗ trợ ra quyết định phân bổ và điều độ phụ tải hợp lý."
        nextSteps={[
          "Trực quan hóa không gian phân cụm (Scatter plot 2D/3D qua PCA)",
          "Đánh giá chất lượng phân cụm với Silhouette Score và Elbow Method",
          "Hiển thị bảng hồ sơ đặc trưng từng cụm (Mùa cao điểm, Nhu cầu trung bình, Mức biến động)",
        ]}
      />
    </AppLayout>
  );
}
