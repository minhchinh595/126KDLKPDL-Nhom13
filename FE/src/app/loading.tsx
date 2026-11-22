import { DashboardSkeleton } from "@/components/dashboard/dashboard-skeleton";
import { AppLayout } from "@/components/layout/app-layout";

export default function Loading() {
  return (
    <AppLayout>
      <DashboardSkeleton />
    </AppLayout>
  );
}
