"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { parseSummary, parseTrend, rangeParams } from "@/lib/analytics-api";
import type { Granularity } from "@/lib/analysis-data";
import { AnalysisWorkspace, ChartFrame, DataTable, ExportCsv, format, Panel, Selector, Stat } from "./analysis-shared";
import { ApiResult } from "./api-result";

function ConsumptionView({ points }: { points: { date: string; value: number }[] }) {
  const [group, setGroup] = useState<Granularity>("day"); const params = rangeParams(points);
  return <div className="space-y-5"><ApiResult endpoint="/api/analysis/summary" params={params} parse={parseSummary}>{summary => <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4"><Stat label="Số quan sát" value={String(summary.sample_count)} detail={`${summary.start_date ?? "—"} – ${summary.end_date ?? "—"}`} /><Stat label="Nhu cầu trung bình" value={`${format(summary.mean)} ${summary.unit}`} detail="MW không được cộng thành MWh" /><Stat label="Quan sát thấp nhất" value={`${format(summary.minimum)} ${summary.unit}`} detail="Trong khoảng đã chọn" /><Stat label="Quan sát cao nhất" value={`${format(summary.maximum)} ${summary.unit}`} detail="Trong khoảng đã chọn" /></div>}</ApiResult>
    <Panel title="Nhu cầu theo kỳ" description="Tuần/tháng hiển thị trung bình các quan sát MW trong kỳ. Dùng metric demand_energy (MWh) khi cần năng lượng.">
      <Selector label="Kỳ tổng hợp" value={group} onChange={value => setGroup(value as Granularity)} options={[{ value: "day", label: "Ngày" }, { value: "week", label: "Tuần" }, { value: "month", label: "Tháng" }]} />
      <ApiResult endpoint="/api/analysis/trend" params={{ ...params, metric: "demand", view: group }} parse={parseTrend}>{result => <div className="space-y-4">{!result.records.length ? <p role="status">Không có dữ liệu trong khoảng đã chọn.</p> : <><ChartFrame label={`Nhu cầu trung bình theo ${group}, ${result.unit}`}><ResponsiveContainer width="100%" height="100%"><BarChart data={result.records}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="period" minTickGap={25} tick={{ fontSize: 11 }} /><YAxis width={70} /><Tooltip formatter={value => `${format(Number(value))} ${result.unit}`} /><Bar dataKey="value" name={`Nhu cầu (${result.unit})`} fill="#3b82f6" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></ChartFrame>
        <ExportCsv filename={`nem-consumption-${group}.csv`} headers={["Period", `Demand (${result.unit})`, "Sample count", "Coverage"]} rows={result.records.map(row => [row.period, row.value, row.sample_count, row.coverage_fraction])} /><DataTable caption="Nhu cầu NEM theo kỳ" headers={["Kỳ", `Nhu cầu (${result.unit})`, "Số mẫu", "Độ phủ"]} rows={result.records.map(row => [row.period, format(row.value), row.sample_count, row.coverage_fraction == null ? "—" : `${format(row.coverage_fraction * 100)}%`])} /></>}</div>}</ApiResult>
    </Panel></div>;
}
export function ConsumptionAnalysis() { return <AnalysisWorkspace kind="consumption">{points => <ConsumptionView points={points} />}</AnalysisWorkspace>; }
