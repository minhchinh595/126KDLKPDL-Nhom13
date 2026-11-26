"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { parseTrend, rangeParams } from "@/lib/analytics-api";
import { AnalysisWorkspace, ChartFrame, DataTable, ExportCsv, format, Panel, Selector, Stat } from "./analysis-shared";
import { ApiResult } from "./api-result";
import type { Granularity } from "@/lib/analysis-data";
import { useState } from "react";

function TrendView({ points }: { points: { date: string; value: number }[] }) {
  const [view, setView] = useState<Granularity>("day");
  return <Panel title="Xu hướng nhu cầu NEM" description="API trả nhu cầu MW theo ngày hoặc trung bình MW trong tuần/tháng; không cộng MW thành năng lượng.">
    <Selector label="Độ phân giải" value={view} onChange={value => setView(value as Granularity)} options={[{ value: "day", label: "Ngày" }, { value: "week", label: "Tuần (trung bình)" }, { value: "month", label: "Tháng (trung bình)" }]} />
    <ApiResult endpoint="/api/analysis/trend" params={{ ...rangeParams(points), metric: "demand", view }} parse={parseTrend}>{result => {
      const rows = result.records;
      const latest = rows.at(-1);
      return <div className="space-y-4"><div className="grid grid-cols-1 sm:grid-cols-3 gap-4"><Stat label="Điểm trong chuỗi" value={String(rows.length)} detail={`${result.view} · ${result.aggregation}`} /><Stat label="Quan sát cuối" value={latest?.value == null ? "—" : `${format(latest.value)} ${result.unit}`} detail={latest?.period ?? "Không có dữ liệu"} /><Stat label="Độ phủ cuối kỳ" value={latest?.coverage_fraction == null ? "—" : `${format(latest.coverage_fraction * 100)}%`} detail={latest ? `${latest.sample_count}/${latest.expected_days} ngày` : "—"} /></div>
        {!rows.length ? <p role="status">Không có điểm xu hướng trong khoảng đã chọn.</p> : <><ChartFrame label={`Nhu cầu NEM ${view}, ${result.unit}`}><ResponsiveContainer width="100%" height="100%"><LineChart data={rows}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="period" minTickGap={35} tick={{ fontSize: 11 }} /><YAxis width={70} /><Tooltip formatter={value => `${format(Number(value))} ${result.unit}`} /><Line type="monotone" dataKey="value" name={`${view === "day" ? "Nhu cầu ngày" : `Trung bình ${view}`} (${result.unit})`} stroke="#f59e0b" strokeWidth={2} dot={false} connectNulls={false} /></LineChart></ResponsiveContainer></ChartFrame>
        <ExportCsv filename={`nem-trend-${view}.csv`} headers={["Period", `Value (${result.unit})`, "Sample count", "Expected days", "Coverage"]} rows={rows.map(row => [row.period, row.value, row.sample_count, row.expected_days, row.coverage_fraction])} /><DataTable caption="Xu hướng NEM" headers={["Kỳ", `Nhu cầu (${result.unit})`, "Số mẫu", "Số ngày kỳ vọng", "Độ phủ"]} rows={rows.map(row => [row.period, format(row.value), row.sample_count, row.expected_days, row.coverage_fraction == null ? "—" : `${format(row.coverage_fraction * 100)}%`])} /></>}
      </div>;
    }}</ApiResult>
  </Panel>;
}
export function TrendAnalysis() { return <AnalysisWorkspace kind="trend">{points => <TrendView points={points} />}</AnalysisWorkspace>; }
