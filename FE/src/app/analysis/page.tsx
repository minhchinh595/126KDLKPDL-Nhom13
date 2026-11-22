import { AppLayout } from "@/components/layout/app-layout";
import { SectionPlaceholder } from "@/components/dashboard/section-placeholder";
import { TrendingUp } from "lucide-react";

export default function AnalysisPage() {
  return (
    <AppLayout>
      <SectionPlaceholder
        title="Phân tích Xu hướng & Quy luật Tiêu thụ"
        subtitle="Khám phá các quy luật tiêu thụ điện năng theo chu kỳ thời gian, thời tiết và tính chất mùa vụ."
        badge="Data Analysis"
        icon={TrendingUp}
        targetObjective="Phân tích xu hướng và quy luật tiêu thụ điện; nhận diện các giai đoạn cao điểm (mùa hè) và thấp điểm (mùa đông / dịp Tết)."
        nextSteps={[
          "Trực quan hóa chi tiết tăng trưởng theo năm (YoY) và theo tháng (MoM)",
          "Phân tích tương quan giữa nhiệt độ/khí hậu và mức tiêu thụ điện năng",
          "Tích hợp các bộ lọc linh hoạt theo giai đoạn năm và loại nguồn phát điện",
        ]}
      />
    </AppLayout>
  );
}
