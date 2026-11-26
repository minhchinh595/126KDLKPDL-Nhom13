"use client";

import { useState, type ReactNode } from "react";
import { ChartNoAxesCombined } from "lucide-react";
import { PageHeading } from "@/components/shared/page-heading";
import Link from "next/link";
import { Download, RotateCcw, SlidersHorizontal } from "lucide-react";
import { AppLayout } from "@/components/layout/app-layout";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { useIsMounted } from "@/hooks/use-mounted";
import { DemandDataGate, DataSourceStatus } from "@/components/dashboard/demand-data-provider";
import { brisbaneDate, type DemandDataset } from "@/lib/demand-api";
import type { DemandPoint } from "@/lib/analysis-data";

export const format = (value: number | null, digits = 2) => value === null ? "—" : value.toLocaleString("vi-VN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
const tabs = [
  { key: "consumption", title: "Consumption Analysis", description: "Tóm tắt nhu cầu daily MW trong khoảng ngày đã chọn." },
  { key: "trend", title: "Trend & Seasonality", description: "Xem xu hướng theo ngày/tuần/tháng và mức trung bình theo weekday." },
  { key: "correlation", title: "Correlation", description: "Khám phá mức độ liên hệ giữa các metric NEM trên ngày được căn chỉnh." },
];
function AnalysisContent({ kind, children, dataset }: {
  kind: string;
  children: (points: DemandPoint[], all: DemandPoint[]) => ReactNode;
  dataset: DemandDataset;
}) {
  const first = dataset.start_date!;
  const last = dataset.end_date!;
  const [start, setStart] = useState(first);
  const [end, setEnd] = useState(last);
  const tab = tabs.find(t => t.key === kind)!;
  const invalid = !start || !end || start > end;
  const allPoints = dataset.records.map(p => ({ date: brisbaneDate(p.observed_at), value: p.value }));
  const points = invalid ? [] : allPoints.filter(p => p.date >= start && p.date <= end);
  function reset() { setStart(first); setEnd(last); }
  return <>
    <div className="space-y-6 min-w-0">
      <PageHeading title={tab.title} description={tab.description} icon={ChartNoAxesCombined} eyebrow="Phân tích Open Electricity NEM · Nhu cầu MW" />
      <nav aria-label="Các trang phân tích" className="flex flex-wrap gap-2">
        {tabs.map(t => <Link key={t.key} href={`/analysis/${t.key}`} aria-current={t.key === kind ? "page" : undefined}
          className={`rounded-lg border px-3 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-ring ${t.key === kind ? "bg-primary text-primary-foreground border-primary" : "border-border hover:bg-muted"}`}>
          {t.title}
        </Link>)}
      </nav>
      <DataSourceStatus data={dataset} />
      <Card className="p-4 gap-4">
        <div className="flex items-center gap-2 text-sm font-semibold"><SlidersHorizontal className="size-4" /> Bộ lọc thời gian</div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="space-y-1 text-sm"> <span className="block">Từ ngày (Brisbane)</span>
            <Input type="date" aria-label="Từ ngày Brisbane" min={first} max={last} value={start} onChange={e => setStart(e.target.value)} aria-invalid={invalid} className="w-44" />
          </label>
          <label className="space-y-1 text-sm"> <span className="block">Đến ngày (Brisbane)</span>
            <Input type="date" aria-label="Đến ngày Brisbane" min={first} max={last} value={end} onChange={e => setEnd(e.target.value)} aria-invalid={invalid} className="w-44" />
          </label>
          <Button variant="outline" onClick={() => { const from = new Date(`${last}T12:00:00Z`); from.setUTCDate(from.getUTCDate() - 29); setStart(from.toISOString().slice(0, 10)); setEnd(last); }}>30 ngày gần nhất</Button>
          <Button variant="ghost" onClick={reset}><RotateCcw /> Đặt lại</Button>
        </div>
        {invalid && <p role="alert" className="text-sm text-destructive">Vui lòng chọn đủ hai mốc; ngày bắt đầu phải trước hoặc bằng ngày kết thúc.</p>}
        <p role="status" className="text-xs text-muted-foreground">Đang chọn {points.length} quan sát · Giờ Australia/Brisbane · Nhu cầu được biểu thị bằng MW, không cộng MW thành điện năng.</p>
      </Card>
      {!points.length ? <Card className="p-8 text-center items-center gap-3"><h2 className="font-semibold">Không có dữ liệu trong khoảng đã chọn</h2><p className="text-sm text-muted-foreground">Điều chỉnh khoảng thời gian hoặc khôi phục toàn bộ dữ liệu.</p><Button onClick={reset}>Khôi phục bộ lọc</Button></Card> : children(points, allPoints)}
    </div>
  </>;
}

export function Selector({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return <label className="space-y-1 text-sm"><span className="block text-muted-foreground">{label}</span><NativeSelect aria-label={label} value={value} onChange={e => onChange(e.target.value)}>{options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</NativeSelect></label>;
}
export function Panel({ title, description, children, actions }: { title: string; description?: string; children: ReactNode; actions?: ReactNode }) {
  return <Card className="p-4 sm:p-6 min-w-0 gap-5"><div className="flex flex-wrap justify-between items-start gap-3"><div className="space-y-1"><h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>{description && <p className="text-xs text-muted-foreground">{description}</p>}</div>{actions}</div>{children}</Card>;
}
export function ChartFrame({ children, label }: { children: ReactNode; label: string }) {
  const mounted = useIsMounted();
  return <div role="img" aria-label={label} className="h-64 sm:h-80 w-full min-w-0">{mounted ? children : <div role="status" className="h-full animate-pulse rounded-lg bg-muted flex items-center justify-center text-sm text-muted-foreground">Đang khởi tạo biểu đồ…</div>}</div>;
}
export function Stat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <Card className="p-5 gap-2 border-t-2 border-t-primary/40"><p className="text-xs text-muted-foreground">{label}</p><p className="text-2xl font-bold tabular-nums">{value}</p><p className="text-xs text-muted-foreground">{detail}</p></Card>;
}
export function DataTable({ headers, rows, caption }: { headers: string[]; rows: ReactNode[][]; caption: string }) {
  return <div tabIndex={0} role="region" aria-label={caption} className="max-h-[32rem] w-full min-w-0 overflow-auto rounded-xl border border-border focus-visible:outline-2 focus-visible:outline-ring"><table className="w-full text-sm whitespace-nowrap"><caption className="sr-only">{caption}</caption><thead className="sticky top-0 z-10 bg-muted"><tr>{headers.map(h => <th key={h} scope="col" className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground border-b border-border">{h}</th>)}</tr></thead><tbody>{rows.map((row, i) => <tr key={i} className="border-b border-border last:border-0 even:bg-muted/20 hover:bg-primary/5 transition-colors">{row.map((cell, j) => <td key={j} className="px-4 py-3 tabular-nums">{cell}</td>)}</tr>)}</tbody></table></div>;
}
export function ExportCsv({ filename, headers, rows }: { filename: string; headers: string[]; rows: (string | number | null)[][] }) {
  function download() {
    const escape = (value: string | number | null) => `"${String(value ?? "").replaceAll('"', '""')}"`;
    const csv = "\uFEFF" + [headers, ...rows].map(row => row.map(escape).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8;" }));
    const a = document.createElement("a"); a.href = url; a.download = filename; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <Button variant="outline" onClick={download}><Download /> Xuất CSV</Button>;
}

export function AnalysisWorkspace({ kind, children }: { kind: string; children: (points: DemandPoint[], all: DemandPoint[]) => ReactNode }) {
  return <AppLayout><DemandDataGate>{data => <AnalysisContent kind={kind} dataset={data}>{children}</AnalysisContent>}</DemandDataGate></AppLayout>;
}
