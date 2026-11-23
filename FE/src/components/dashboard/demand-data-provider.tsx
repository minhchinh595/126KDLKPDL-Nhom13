"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { fetchDemandDataset, type DemandDataset } from "@/lib/demand-api";
import { DashboardSkeleton } from "./dashboard-skeleton";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type LoadState = { status: "loading" } | { status: "error"; message: string } | { status: "success"; data: DemandDataset };
const Context = createContext<{ state: LoadState; reload: () => void } | null>(null);

export function DemandDataProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [request, setRequest] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    fetchDemandDataset({ signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({ status: "success", data });
    }).catch(error => {
      if (!controller.signal.aborted) setState({ status: "error", message: error instanceof Error ? error.message : "Không tải được dữ liệu biểu đồ." });
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
  if (state.status === "error") return <Card className="p-6 space-y-3" role="alert"><h1 className="text-xl font-semibold">Không tải được dữ liệu biểu đồ</h1><p className="text-sm text-muted-foreground">{state.message}</p><Button onClick={reload}>Thử lại kết nối API</Button></Card>;
  if (!state.data.records.length) return <Card className="p-6 space-y-3" role="status"><h1 className="text-xl font-semibold">API chưa có dữ liệu tiêu thụ</h1><p className="text-sm text-muted-foreground">Nguồn: {state.data.source}. Hãy kiểm tra dataset trên backend.</p><Button onClick={reload}>Tải lại dữ liệu</Button></Card>;
  return children(state.data);
}

export function DataSourceStatus({ data }: { data: DemandDataset }) {
  const { reload } = useDemandData();
  return <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-blue-500/30 bg-blue-500/5 p-3 text-sm">
    <p className="min-w-0 break-words"><strong>Dữ liệu từ API.</strong> {data.total} tháng ({data.start_month} – {data.end_month}) · {data.iso3} · {data.unit}. Nguồn: {data.source}.</p>
    <Button variant="outline" onClick={reload}>Tải lại từ API</Button>
  </div>;
}
