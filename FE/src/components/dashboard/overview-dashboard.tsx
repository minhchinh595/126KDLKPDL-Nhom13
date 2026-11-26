"use client";

import { useState } from "react";
import Link from "next/link";
import { Activity, ArrowRight, CalendarDays, Flame, RotateCcw, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { MetricCard } from "./metric-card";
import { DemandDataGate, DataSourceStatus } from "./demand-data-provider";
import type { DemandDataset } from "@/lib/demand-api";
import { brisbaneDate } from "@/lib/demand-api";
import { OverviewDistribution, OverviewSeasonality, OverviewTrendChart } from "./overview-charts";
import { DataTable, ExportCsv, format, Panel } from "@/components/analysis/analysis-shared";
import { filterDemand } from "@/lib/analysis-data";
import { ApiResult } from "@/components/analysis/api-result";
import { parseDashboard, parseDemandStatistics, rangeParams, type DashboardResult } from "@/lib/analytics-api";
import { ForecastPreview } from "@/components/models/model-workspace";

function OverviewContent({ dataset, overview }: { dataset: DemandDataset; overview: DashboardResult }) {
  const first = dataset.start_date ?? ""; const last = dataset.end_date ?? "";
  const [start, setStart] = useState(first); const [end, setEnd] = useState(last);
  const invalid = !start || !end || start > end;
  const points = filterDemand(dataset.records.map(row => ({ date: brisbaneDate(row.observed_at), value: row.value })), start, end);
  const observedAt = overview.latest_data_timestamp ? new Date(overview.latest_data_timestamp).toLocaleString("vi-VN", { timeZone: "Australia/Brisbane" }) : "—";
  function reset() { setStart(first); setEnd(last); }
  return <div className="space-y-4 min-w-0">
    <div className="flex flex-wrap items-end justify-between gap-3"><div><h1 className="text-2xl font-semibold tracking-tight">Overview Dashboard</h1><p className="mt-1 text-sm text-muted-foreground">Nhu cầu điện NEM hằng ngày, các chỉ số thị trường và trạng thái dữ liệu.</p></div><Button variant="outline" onClick={reset}><RotateCcw /> Đặt lại khoảng ngày</Button></div>
    <DataSourceStatus data={dataset} />
    <Card className="p-3 gap-2"><div className="flex flex-wrap items-end gap-3"><div className="flex items-center gap-2 self-center text-sm font-semibold lg:mr-2"><CalendarDays className="size-4" /> Khoảng ngày Brisbane</div>
      <label className="space-y-1 text-sm"><span className="block">Từ ngày</span><Input className="h-9 w-40" type="date" min={first} max={last} value={start} aria-invalid={invalid} onChange={event => setStart(event.target.value)} /></label>
      <label className="space-y-1 text-sm"><span className="block">Đến ngày</span><Input className="h-9 w-40" type="date" min={first} max={last} value={end} aria-invalid={invalid} onChange={event => setEnd(event.target.value)} /></label>
      <Button variant="outline" onClick={() => { const from = new Date(`${last}T12:00:00Z`); from.setUTCDate(from.getUTCDate() - 29); setStart(from.toISOString().slice(0, 10)); setEnd(last); }}>30 ngày gần nhất</Button>
    </div>{invalid && <p role="alert" className="text-sm text-destructive">Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.</p>}<p role="status" className="text-xs text-muted-foreground">{points.length} quan sát demand trong khoảng · đơn vị MW · timezone Australia/Brisbane.</p></Card>
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
      <MetricCard title="Nhu cầu ngày mới nhất" value={format(overview.latest_daily_demand_mw)} unit="MW" description="Theo dữ liệu demand NEM" icon={Zap} variant="amber" />
      <MetricCard title="Nhu cầu trung bình ngày" value={format(overview.average_daily_demand_mw)} unit="MW" description="Theo dữ liệu NEM hiện có" icon={Activity} variant="purple" />
      <MetricCard title="Nhu cầu thấp nhất ngày" value={format(overview.minimum_daily_demand_mw)} unit="MW" description="Theo dữ liệu NEM hiện có" icon={CalendarDays} variant="blue" />
      <MetricCard title="Nhu cầu cao nhất ngày" value={format(overview.maximum_daily_demand_mw)} unit="MW" description="Theo dữ liệu NEM hiện có" icon={Flame} variant="emerald" />
    </div>
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <MetricCard title="Tỷ trọng năng lượng tái tạo mới nhất" value={format(overview.latest_renewable_proportion_percent)} unit="%" description="Dữ liệu daily network-level" icon={Activity} />
      <MetricCard title="Giá điện mới nhất" value={format(overview.latest_price_per_mwh)} unit="$/MWh" description="Có thể âm theo giá thị trường" icon={Zap} />
      <MetricCard title="Tổng số bản ghi" value={overview.total_observations.toLocaleString("vi-VN")} description={`${dataset.dataset_name} · ${dataset.interval} · Thời điểm dữ liệu mới nhất: ${observedAt}`} icon={CalendarDays} />
    </div>
    {!invalid && points.length > 0 && <ApiResult endpoint="/api/electricity/demand/statistics" params={{ ...rangeParams(points), interval: "1d" }} parse={parseDemandStatistics}>{statistics => <Panel title="Thống kê nhu cầu trong khoảng chọn" description={`${start} – ${end} · trung bình MW/quan sát`}><div className="grid grid-cols-2 xl:grid-cols-4 gap-4"><MetricCard title="Số quan sát" value={statistics.count} description="Observation được trả về, không nội suy" icon={CalendarDays} /><MetricCard title="Trung bình" value={format(statistics.mean)} unit="MW" description="Gateway NEM demand statistics" icon={Activity} /><MetricCard title="Thấp nhất" value={format(statistics.minimum)} unit="MW" description="Trong khoảng chọn" icon={Zap} /><MetricCard title="Cao nhất" value={format(statistics.maximum)} unit="MW" description="Trong khoảng chọn" icon={Flame} /></div></Panel>}</ApiResult>}
    {!invalid && points.length > 0 && <Panel title="Xu hướng nhu cầu điện" description="Chuỗi daily MW; các giá trị tuần/tháng là mức trung bình, không cộng MW thành MWh."><OverviewTrendChart points={points} /></Panel>}
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
      <Panel title="Mẫu theo ngày trong tuần" description="Trung bình theo weekday; đây không phải seasonality theo tháng trong năm."><OverviewSeasonality points={points} /></Panel>
      <Panel title="Phân bố nhu cầu hằng ngày" description="Histogram từ NEM Analysis API, đơn vị MW."><OverviewDistribution points={points} /></Panel>
    </div>
    <Panel title="Quan sát nhu cầu chi tiết" description="Ngày được định dạng theo Australia/Brisbane; danh sách dựa trên dữ liệu Gateway.">
      <ExportCsv filename={`nem-demand-${start}-${end}.csv`} headers={["Ngày Brisbane", "Dataset", "Network", "Metric", "Interval", "Demand (MW)"]} rows={points.map(point => [point.date, dataset.dataset_name, dataset.network_code, dataset.metric, dataset.interval, point.value])} />
      <DataTable caption="Nhu cầu NEM theo ngày" headers={["Ngày Brisbane", "Nhu cầu (MW)"]} rows={[...points].reverse().slice(0, 100).map(point => [point.date, format(point.value)])} />
      <p className="text-xs text-muted-foreground">Hiển thị tối đa 100 ngày gần nhất trong bảng; CSV xuất toàn bộ khoảng ngày đã chọn.</p>
    </Panel>
    <Panel title="Dự báo nhu cầu mới nhất" description="Kết quả model đã lưu trên Gateway; không tạo dự báo giả khi chưa có run hoàn tất."><ForecastPreview /></Panel>
    <Link href="/analysis/trend" className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline underline-offset-4">Mở phân tích chi tiết <ArrowRight className="size-3" /></Link>
  </div>;
}

export function OverviewDashboard() {
  return <DemandDataGate>{dataset => <ApiResult endpoint="/api/dashboard/overview" parse={parseDashboard}>{overview => <OverviewContent dataset={dataset} overview={overview} />}</ApiResult>}</DemandDataGate>;
}
