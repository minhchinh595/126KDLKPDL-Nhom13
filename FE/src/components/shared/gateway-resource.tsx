"use client";
import { useEffect, useState, type ReactNode } from "react";
import { LoaderCircle, Inbox, CircleAlert, ChevronLeft, ChevronRight } from "lucide-react";
import { gatewayRequest } from "@/lib/gateway";
import { DemandApiError } from "@/lib/demand-api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function useGatewayQuery<T>(path: string | null, revision = 0) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: T; error?: Error; status: "success" | "error" | "empty" } | null>(null);
  const key = `${path}#${revision}#${attempt}`;
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    gatewayRequest<T>(path, { signal: controller.signal }).then(data => { if (!controller.signal.aborted) setResult({ key, data, status: "success" }); }).catch(error => {
      if (!controller.signal.aborted) setResult({ key, status: error instanceof DemandApiError && error.status === 404 ? "empty" : "error", error: error instanceof Error ? error : new Error("Không tải được dữ liệu.") });
    });
    return () => controller.abort();
  }, [path, key]);
  return { status: !path ? "idle" as const : !result || result.key !== key ? "loading" as const : result.status, data: result?.key === key ? result.data : undefined, error: result?.key === key ? result.error : undefined, retry: () => setAttempt(value => value + 1) };
}
export function QueryState<T>({ resource, children, empty = "Chưa có dữ liệu." }: { resource: ReturnType<typeof useGatewayQuery<T>>; children: (data: T) => ReactNode; empty?: string }) {
  if (resource.status === "idle") return null;
  if (resource.status === "loading") return <div role="status" className="flex items-center justify-center gap-2 rounded-xl bg-muted/40 p-6 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin" />Đang tải dữ liệu…</div>;
  if (resource.status === "empty") return <div role="status" className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border px-5 py-8 text-center text-sm text-muted-foreground"><Inbox className="size-8 text-muted-foreground/60" /><p className="max-w-md">{empty}</p></div>;
  if (resource.status === "error") return <Card role="alert" className="p-5 gap-3 border-destructive/20 bg-destructive/5"><CircleAlert className="size-5 text-destructive" /><p className="text-sm text-destructive">{resource.error?.message}</p><Button variant="outline" onClick={resource.retry}>Thử lại</Button></Card>;
  return children(resource.data as T);
}
export function Pagination({ page, pages, total, onChange }: { page: number; pages: number; total: number; onChange: (page: number) => void }) {
  return <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4 text-xs text-muted-foreground"><span>{total} kết quả · Trang {page}/{Math.max(1, pages)}</span><div className="flex gap-2"><Button variant="outline" disabled={page <= 1} onClick={() => onChange(page - 1)}><ChevronLeft className="size-4" />Trước</Button><Button variant="outline" disabled={page >= pages} onClick={() => onChange(page + 1)}>Sau<ChevronRight className="size-4" /></Button></div></div>;
}
