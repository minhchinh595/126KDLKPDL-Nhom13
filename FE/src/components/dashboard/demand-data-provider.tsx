"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { DemandApiError, fetchDemandDataset, type DemandDataset } from "@/lib/demand-api";
import { DemandLogin } from "./demand-login";
import { DashboardSkeleton } from "./dashboard-skeleton";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Database, RefreshCw } from "lucide-react";

type LoadState = { status: "loading" } | { status: "error"; message: string; httpStatus?: number } | { status: "success"; data: DemandDataset };
const Context = createContext<{ state: LoadState; reload: () => void } | null>(null);

export function DemandDataProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [request, setRequest] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    fetchDemandDataset({ signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({ status: "success", data });
    }).catch(error => {
      if (!controller.signal.aborted) setState({ status: "error", httpStatus: error instanceof DemandApiError ? error.status : undefined, message: error instanceof Error ? error.message : "Không tải được dữ liệu biểu đồ." });
    });
    return () => controller.abort();
  }, [request]);
  function reload() { setState({ status: "loading" }); setRequest(n => n + 1); }
  return <Context.Provider value={{ state, reload }}>{children}</Context.Provider>;
}

export function useDemandData() {
  const context = useContext(Context);
  if (!context) throw new Error("DemandDataProvider is required");
  return context;
}

export function DemandDataGate({ children }: { children: (data: DemandDataset) => ReactNode }) {
  const { state, reload } = useDemandData();
  if (state.status === "loading") return <div role="status" aria-label="Đang tải dữ liệu biểu đồ từ API"><DashboardSkeleton /></div>;
  if (state.status === "error" && state.httpStatus === 401) return <DemandLogin onSuccess={reload} />;
  if (state.status === "error") return <Card className="p-6 space-y-3" role="alert"><h1 className="text-xl font-semibold">Không tải được dữ liệu biểu đồ</h1><p className="text-sm text-muted-foreground">{state.message}</p><Button onClick={reload}>Thử lại kết nối API</Button></Card>;
  if (!state.data.records.length) return <Card className="p-6 space-y-3" role="status"><h1 className="text-xl font-semibold">API chưa có dữ liệu tiêu thụ</h1><p className="text-sm text-muted-foreground">Nguồn: {state.data.source}. Hãy kiểm tra dataset trên backend.</p><Button onClick={reload}>Tải lại dữ liệu</Button></Card>;
  return children(state.data);
}

export function DataSourceStatus({ data }: { data: DemandDataset }) {
  const { reload } = useDemandData();
  const monthLabel = (month: string | null) => month ? month.split("-").reverse().join("/") : "—";
  return <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 rounded-lg border border-border bg-card px-3 py-2 text-xs text-muted-foreground">
    <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2">
      <p className="inline-flex flex-wrap items-center gap-2 py-1"><Database className="size-3.5 text-primary" /><span><strong className="font-semibold text-foreground">{data.total} tháng</strong> · {monthLabel(data.start_month)}–{monthLabel(data.end_month)} · {data.unit}</span></p>
      <details className="min-w-0"><summary className="cursor-pointer py-1 hover:text-foreground">Chi tiết nguồn</summary><p className="max-w-lg break-words pb-1">{data.iso3} · Nguồn: {data.source}</p></details>
    </div>
    <Button variant="ghost" size="sm" onClick={reload}><RefreshCw className="size-3.5" />Tải lại từ API</Button>
  </div>;
}
