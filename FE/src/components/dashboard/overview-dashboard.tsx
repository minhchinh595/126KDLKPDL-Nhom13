"use client";

import { useState } from "react";
import Link from "next/link";
import { Activity, ArrowRight, CalendarDays, ChevronLeft, ChevronRight, Flame, RotateCcw, Search, SlidersHorizontal, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { MetricCard } from "./metric-card";
import { DemandDataGate, DataSourceStatus } from "./demand-data-provider";
import type { DemandDataset } from "@/lib/demand-api";
import { OverviewDistribution, OverviewSeasonality, OverviewTrendChart } from "./overview-charts";
import { DataTable, ExportCsv, format, Panel, Selector } from "@/components/analysis/analysis-shared";
import { DEMAND_LEVELS, filterDemand, monthlyChanges, summarizeDemand } from "@/lib/analysis-data";

const csvHeaders = ["Tháng", "Quốc gia", "Tiêu thụ (TWh)", "MoM (%)", "YoY (%)", "Mức tiêu thụ"];
const percent = (value: number | null) => value === null ? "—" : `${value > 0 ? "+" : ""}${format(value)}%`;
const detailLink = "inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline underline-offset-4";

function OverviewContent({ dataset }: { dataset: DemandDataset }) {
  const first = dataset.records[0].month;
  const last = dataset.records[dataset.records.length - 1].month;
  const [start, setStart] = useState(first);
  const [end, setEnd] = useState(last);
  const [compare, setCompare] = useState(true);
  const [search, setSearch] = useState("");
  const [level, setLevel] = useState("all");
  const [sort, setSort] = useState("newest");
  const [pageSize, setPageSize] = useState(10);
  const [page, setPage] = useState(1);
  const invalid = !start || !end || start > end;
  const points = filterDemand(dataset.records, start, end);
  const summary = summarizeDemand(points, dataset.records);
  const rows = monthlyChanges(points, dataset.records)
    .filter(p => p.month.includes(search.trim()) && (level === "all" || p.level === level))
    .sort((a, b) => sort === "oldest" ? a.month.localeCompare(b.month) : sort === "highest" ? b.value - a.value : sort === "lowest" ? a.value - b.value : b.month.localeCompare(a.month));
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const visible = rows.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const latest = summary.latest;
  function range(from: string, to: string) { setStart(from); setEnd(to); setPage(1); }
  function reset() { range(first, last); setSearch(""); setLevel("all"); setSort("newest"); setPageSize(10); setCompare(true); }
  function tableReset() { setSearch(""); setLevel("all"); setSort("newest"); setPage(1); }


  return <div className="space-y-6 min-w-0">
    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 border-b border-border pb-5">
      <div className="space-y-2">
        <p className="text-xs uppercase tracking-wider font-semibold text-amber-600">Electricity Analytics · Việt Nam</p>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Overview Dashboard</h1>
        <p className="text-sm text-muted-foreground">Theo dõi tiêu thụ điện, xu hướng và các giai đoạn cao điểm trong một màn hình.</p>
      </div>
      <Button variant="outline" onClick={reset}><RotateCcw /> Đặt lại Dashboard</Button>
    </div>

    <DataSourceStatus data={dataset} />

    <Card className="p-4 gap-4">
      <div className="flex items-center gap-2 text-sm font-semibold"><SlidersHorizontal className="size-4" /> Bộ lọc Dashboard</div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="space-y-1 text-sm"><span className="block">Từ tháng</span><Input className="w-44" type="month" aria-label="Từ tháng" min={first} max={last} value={start} aria-invalid={invalid} aria-describedby={invalid ? "overview-range-error" : undefined} onChange={e => range(e.target.value, end)} /></label>
        <label className="space-y-1 text-sm"><span className="block">Đến tháng</span><Input className="w-44" type="month" aria-label="Đến tháng" min={first} max={last} value={end} aria-invalid={invalid} aria-describedby={invalid ? "overview-range-error" : undefined} onChange={e => range(start, e.target.value)} /></label>
        <Button variant="outline" onClick={() => range(dataset.records[Math.max(0, dataset.records.length - 12)]?.month ?? first, last)}>12 tháng gần nhất</Button>
        <Button variant="outline" onClick={() => range(`${last.slice(0, 4)}-01`, last)}>Năm dữ liệu mới nhất</Button>
        <Button variant="ghost" onClick={() => range(first, last)}>Toàn bộ</Button>
      </div>
      {invalid && <p id="overview-range-error" role="alert" className="text-sm text-destructive">Chọn đủ hai mốc thời gian, tháng bắt đầu phải trước hoặc bằng tháng kết thúc.</p>}
      <p role="status" className="text-xs text-muted-foreground">{points.length} tháng được chọn · KPI, biểu đồ lịch sử và bảng dữ liệu dùng chung khoảng lọc.</p>
    </Card>

    {!points.length ? <Card className="p-8 items-center text-center gap-3"><CalendarDays className="size-8 text-muted-foreground" /><h2 className="font-semibold">Không có dữ liệu trong khoảng đã chọn</h2><p className="text-sm text-muted-foreground">Dữ liệu hiện có từ {first} đến {last}.</p><Button onClick={reset}>Khôi phục toàn bộ dữ liệu</Button></Card> : <>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <MetricCard title="Tiêu thụ tháng cuối kỳ" value={format(latest!.value)} unit="TWh" trend={latest!.yoy === null ? undefined : Number(latest!.yoy.toFixed(2))} description={`${latest!.month} · ${latest!.yoy === null ? "Chưa có cùng kỳ" : "so với cùng kỳ năm trước"}`} icon={Zap} variant="amber" />
        <MetricCard title="Tổng tiêu thụ trong kỳ" value={format(summary.total)} unit="TWh" description={`${summary.count} tháng có dữ liệu`} icon={CalendarDays} variant="purple" />
        <MetricCard title="Tiêu thụ trung bình tháng" value={format(summary.average)} unit="TWh" description="Trung bình của khoảng đã chọn" icon={Activity} variant="blue" />
        <MetricCard title="Tháng tiêu thụ cao nhất" value={format(summary.peak!.value)} unit="TWh" description={`Ghi nhận tại ${summary.peak!.month}`} icon={Flame} variant="emerald" />
      </div>

      <Panel title="Xu hướng tiêu thụ điện" description={`${points[0].month} – ${points[points.length - 1].month} · TWh/tháng. Cùng kỳ được tra từ toàn bộ lịch sử.`}
        actions={<label className="inline-flex items-center gap-2 text-xs cursor-pointer"><input type="checkbox" checked={compare} onChange={e => setCompare(e.target.checked)} className="size-4 accent-amber-500" /> So sánh cùng kỳ năm trước</label>}>
        <OverviewTrendChart points={points} all={dataset.records} compare={compare} />
        <Link href="/analysis/consumption" className={detailLink}>Mở Consumption Analysis <ArrowRight className="size-3" /></Link>
      </Panel>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Panel title="Quy luật tiêu thụ theo tháng" description="Trung bình các tháng cùng tên trong khoảng lọc; chưa điều chỉnh xu hướng giữa các năm.">
          <OverviewSeasonality points={points} />
          {points.length < 24 && <p className="text-xs text-muted-foreground">Dưới 24 tháng dữ liệu: chưa đủ nhiều chu kỳ để kết luận về mùa vụ.</p>}
          <Link href="/analysis/trend" className={detailLink}>Mở Trend & Seasonality <ArrowRight className="size-3" /></Link>
        </Panel>
        <Panel title="Phân bố mức tiêu thụ" description="Phân nhóm theo ngưỡng cố định để quan sát dữ liệu, chưa phải kết quả K-Means.">
          <OverviewDistribution points={points} />
          <p className="text-xs text-muted-foreground">Các ngưỡng phục vụ minh họa giao diện; không phải ngưỡng cảnh báo vận hành.</p>
        </Panel>
      </div>

      <Panel title="Điểm nổi bật trong kỳ" description="Các nhận xét được tính lại khi đổi khoảng thời gian.">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div className="rounded-lg bg-muted/40 p-4 space-y-2"><p className="font-medium">Tháng thấp nhất</p><p className="text-muted-foreground">{summary.low!.month}: <strong className="text-foreground">{format(summary.low!.value)} TWh</strong>. Chênh lệch đỉnh / đáy: {format(summary.peak!.value - summary.low!.value)} TWh.</p></div>
          <div className="rounded-lg bg-muted/40 p-4 space-y-2"><p className="font-medium">Biến động tháng cuối kỳ</p><p className="text-muted-foreground">MoM: <strong className="text-foreground">{percent(latest!.mom)}</strong> · YoY: <strong className="text-foreground">{percent(latest!.yoy)}</strong>. Dấu — nghĩa là chưa đủ dữ liệu đối chiếu.</p></div>
          <div className="rounded-lg bg-muted/40 p-4 space-y-2"><p className="font-medium">Khám phá mối liên hệ</p><p className="text-muted-foreground">So sánh mức tiêu thụ với tháng trước hoặc cùng kỳ năm trước.</p><Link href="/analysis/correlation" className={detailLink}>Mở Correlation <ArrowRight className="size-3" /></Link></div>
        </div>
      </Panel>

      <Panel title="Dữ liệu tiêu thụ chi tiết" description="Bộ lọc bên dưới chỉ áp dụng cho bảng và CSV; không thay đổi KPI hay biểu đồ. MoM/YoY dùng lịch sử đầy đủ."
        actions={<ExportCsv filename={`overview-${start}-${end}.csv`} headers={csvHeaders} rows={rows.map(p => [p.month, "Việt Nam", p.value, p.mom, p.yoy, DEMAND_LEVELS.find(l => l.key === p.level)!.label])} />}>
        <div className="flex flex-wrap items-end gap-3">
          <label className="space-y-1 text-sm"><span className="flex items-center gap-1 text-muted-foreground"><Search className="size-3" /> Tìm tháng</span><Input aria-label="Tìm tháng trong bảng" placeholder="Ví dụ: 2026 hoặc 2026-09" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} className="w-60 max-w-full" /></label>
          <Selector label="Mức tiêu thụ" value={level} onChange={v => { setLevel(v); setPage(1); }} options={[{ value: "all", label: "Tất cả mức" }, ...DEMAND_LEVELS.map(l => ({ value: l.key, label: `${l.label} · ${l.range}` }))]} />
          <Selector label="Sắp xếp" value={sort} onChange={v => { setSort(v); setPage(1); }} options={[{ value: "newest", label: "Tháng mới nhất" }, { value: "oldest", label: "Tháng cũ nhất" }, { value: "highest", label: "Tiêu thụ giảm dần" }, { value: "lowest", label: "Tiêu thụ tăng dần" }]} />
          <Selector label="Số dòng / trang" value={String(pageSize)} onChange={v => { setPageSize(Number(v)); setPage(1); }} options={[10, 20, 50].map(n => ({ value: String(n), label: String(n) }))} />
        </div>
        {rows.length ? <DataTable caption="Tiêu thụ hàng tháng và tăng trưởng so với tháng trước, cùng kỳ năm trước" headers={csvHeaders} rows={visible.map(p => [p.month, "Việt Nam", format(p.value), percent(p.mom), percent(p.yoy), <span key={p.month} className="inline-flex items-center gap-2"><span className="size-2 rounded-full" style={{ backgroundColor: DEMAND_LEVELS.find(l => l.key === p.level)!.color }} />{DEMAND_LEVELS.find(l => l.key === p.level)!.label}</span>])} /> : <div role="status" className="py-8 text-center space-y-3"><p className="text-sm text-muted-foreground">Không có bản ghi phù hợp với bộ lọc bảng.</p><Button variant="outline" onClick={tableReset}>Xóa bộ lọc bảng</Button></div>}
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
          <p role="status">{rows.length ? `${(currentPage - 1) * pageSize + 1}–${Math.min(currentPage * pageSize, rows.length)}` : "0"} / {rows.length} bản ghi · CSV xuất toàn bộ kết quả lọc</p>
          <div className="flex items-center gap-2"><Button aria-label="Trang trước" variant="outline" size="sm" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}><ChevronLeft /></Button><span>Trang {currentPage}/{pageCount}</span><Button aria-label="Trang sau" variant="outline" size="sm" disabled={currentPage >= pageCount} onClick={() => setPage(currentPage + 1)}><ChevronRight /></Button></div>
        </div>
      </Panel>
    </>}

    <Panel title="Dự báo nhu cầu" description="Chưa có API mô hình dự báo.">
      <p className="text-sm text-muted-foreground">Các biểu đồ lịch sử phía trên sử dụng dữ liệu từ API. Dự báo sẽ được hiển thị khi backend cung cấp kết quả mô hình; hiện không hiển thị chuỗi dự báo mẫu.</p>
    </Panel>
  </div>;
}

export function OverviewDashboard() {
  return <DemandDataGate>{data => <OverviewContent dataset={data} />}</DemandDataGate>;
}
