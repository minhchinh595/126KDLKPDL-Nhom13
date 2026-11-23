"use client";

import { AppLayout } from "@/components/layout/app-layout";
import { Button } from "@/components/ui/button";

export default function DashboardError({ retry }: { error: unknown; retry: () => void }) {
  return <AppLayout><div role="alert" className="rounded-lg border border-border p-6 space-y-3">
    <h1 className="text-xl font-semibold">Không thể hiển thị nội dung</h1>
    <p className="text-sm text-muted-foreground">Có lỗi khi hiển thị dữ liệu. Hãy thử tải lại nội dung.</p>
    <Button onClick={retry}>Thử lại</Button>
  </div></AppLayout>;
}
