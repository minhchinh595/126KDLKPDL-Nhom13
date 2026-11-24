"use client";

import { useEffect, useState, type ReactNode } from "react";
import { analyticsPath, fetchAnalytics, type AnalyticsEndpoint, type AnalyticsParams } from "@/lib/analytics-api";
import { DemandApiError } from "@/lib/demand-api";
import { DemandLogin } from "@/components/dashboard/demand-login";
import { useDemandData } from "@/components/dashboard/demand-data-provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type Result<T> = { key: string; status: "success"; data: T } | { key: string; status: "error"; error: unknown };
export function ApiResult<T>({ endpoint, params = {}, parse, children }: { endpoint: AnalyticsEndpoint; params?: AnalyticsParams; parse: (input: unknown) => T; children: (data: T) => ReactNode }) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<Result<T> | null>(null);
  const { reload } = useDemandData();
  const path = analyticsPath(endpoint, params);
  const key = `${path}#${attempt}`;
  useEffect(() => {
    const controller = new AbortController();
    const query = Object.fromEntries(new URLSearchParams(path.split("?")[1] ?? ""));
    fetchAnalytics(endpoint, query, parse, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({ key, status: "success", data });
    }).catch(error => {
      if (!controller.signal.aborted) setState({ key, status: "error", error });
    });
    return () => controller.abort();
  }, [endpoint, path, key, parse]);
  if (!state || state.key !== key) return <Card className="p-6 animate-pulse" role="status">Đang tải kết quả phân tích…</Card>;
  if (state.status === "success") return children(state.data);
  if (state.error instanceof DemandApiError && state.error.status === 401) return <DemandLogin onSuccess={reload} />;
  return <Card className="p-5 gap-3" role="alert"><h2 className="font-semibold">Không tải được kết quả phân tích</h2><p className="text-sm text-muted-foreground">{state.error instanceof Error ? state.error.message : "Có lỗi khi gọi API."}</p><Button variant="outline" onClick={() => setAttempt(n => n + 1)}>Thử lại</Button></Card>;
}
