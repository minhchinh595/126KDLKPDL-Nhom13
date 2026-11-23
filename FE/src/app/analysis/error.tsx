"use client";

import { AppLayout } from "@/components/layout/app-layout";
import { Button } from "@/components/ui/button";

export default function AnalysisError({ retry }: { error: unknown; retry: () => void }) {
  return <AppLayout><div role="alert" className="rounded-lg border border-border p-6 space-y-3"><h1 className="text-xl font-semibold">Không thể hiển thị trang phân tích</h1><p className="text-sm text-muted-foreground">Có lỗi khi xử lý hoặc hiển thị dữ liệu. Vui lòng thử tải lại trang.</p><Button onClick={retry}>Thử lại</Button></div></AppLayout>;
}
