"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { parseDistribution, parseSeasonality, rangeParams, seasonalityWeekdayLabel, seasonalityWeekdayRows } from "@/lib/analytics-api";
import type { DemandPoint } from "@/lib/analysis-data";
import { ApiResult } from "./api-result";
import { ChartFrame, DataTable, ExportCsv, format, Selector } from "./analysis-shared";

const tooltipStyle = { background: "var(--card)", borderColor: "var(--border)", borderRadius: 8, color: "var(--foreground)" };
export function SeasonalityApiChart({ points }: { points: DemandPoint[] }) {
  return <ApiResult endpoint="/api/analysis/seasonality" params={rangeParams(points)} parse={parseSeasonality}>{result => { const rows = seasonalityWeekdayRows(result.records); return <div className="space-y-4">
    <ChartFrame label="Nhu cầu trung bình theo weekday, MW"><ResponsiveContainer width="100%" height="100%"><LineChart data={rows.map(row => ({ ...row, weekday_name: seasonalityWeekdayLabel(row.weekday) }))}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" /><XAxis dataKey="weekday_name" tick={{ fontSize: 11 }} /><YAxis width={70} /><Tooltip contentStyle={tooltipStyle} formatter={value => value == null ? "Không có quan sát" : `${format(Number(value))} ${result.unit}`} /><Line dataKey="mean" name="Nhu cầu trung bình" stroke="#f59e0b" strokeWidth={3} connectNulls={false} /></LineChart></ResponsiveContainer></ChartFrame>
    <p className="text-xs text-muted-foreground">{result.limitation} · Phân nhóm theo weekday, không phải chu kỳ mùa vụ năm.</p>
    <DataTable caption="Nhu cầu theo ngày trong tuần" headers={["Ngày trong tuần", "Số quan sát", `Trung bình (${result.unit})`]} rows={rows.map(row => [seasonalityWeekdayLabel(row.weekday), row.count, format(row.mean)])} />
  </div>; }}</ApiResult>;
}

export function DistributionApiChart({ points }: { points: DemandPoint[] }) {
  const [bins, setBins] = useState(10);
  return <div className="space-y-4"><Selector label="Số khoảng phân bố" value={String(bins)} onChange={value => setBins(Number(value))} options={[5, 10, 15, 20].map(value => ({ value: String(value), label: `${value} khoảng` }))} />
    <ApiResult endpoint="/api/analysis/distribution" params={{ ...rangeParams(points), metric: "demand", interval: "1d", bins }} parse={parseDistribution}>{result => {
      if (!result.sample_count) return <p role="status" className="text-sm text-muted-foreground">Không có dữ liệu phân bố trong khoảng đã chọn.</p>;
      return <div className="space-y-4"><ChartFrame label={`Histogram nhu cầu daily (${result.unit ?? "đơn vị chưa có"})`}><ResponsiveContainer width="100%" height="100%"><BarChart data={result.bins.map(bin => ({ ...bin, range: `${format(bin.start, 0)}–${format(bin.end, 0)}` }))}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" /><XAxis dataKey="range" minTickGap={12} tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} /><Tooltip contentStyle={tooltipStyle} /><Bar dataKey="count" name="Số quan sát" fill="#3b82f6" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></ChartFrame>
        <ExportCsv filename="nem-demand-distribution.csv" headers={[`Từ (${result.unit})`, `Đến (${result.unit})`, "Số quan sát"]} rows={result.bins.map(bin => [bin.start, bin.end, bin.count])} />
        <DataTable caption="Histogram nhu cầu NEM" headers={[`Từ (${result.unit})`, `Đến (${result.unit})`, "Số quan sát"]} rows={result.bins.map(bin => [format(bin.start, 2), format(bin.end, 2), bin.count])} /><p className="text-xs text-muted-foreground">{result.sample_count} quan sát; đây là phân bố nhu cầu, không phải kết quả clustering.</p>
      </div>;
    }}</ApiResult>
  </div>;
}
