"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { parseDistribution, parseSeasonality, rangeParams } from "@/lib/analytics-api";
import type { DemandPoint } from "@/lib/analysis-data";
import { ApiResult } from "./api-result";
import { ChartFrame, DataTable, ExportCsv, format, Selector } from "./analysis-shared";

const tooltipStyle = { background: "var(--card)", borderColor: "var(--border)", borderRadius: 8, color: "var(--foreground)" };
export function SeasonalityApiChart({ points }: { points: DemandPoint[] }) {
  return <ApiResult endpoint="/api/analysis/seasonality" params={rangeParams(points)} parse={parseSeasonality}>{result => {
    const rows = result.records.map(row => ({ ...row, month: `T${row.month_number}` }));
    const headers = ["Tháng", "Số quan sát", "Trung bình (TWh)", "Trung vị (TWh)", "Thấp nhất (TWh)", "Cao nhất (TWh)"];
    return <div className="space-y-4">
      <ChartFrame label="Trung bình, thấp nhất và cao nhất theo tháng, từ API mùa vụ">
        <ResponsiveContainer width="100%" height="100%"><LineChart data={rows} margin={{ top: 12, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" /><XAxis dataKey="month" tick={{ fontSize: 11 }} /><YAxis width={60} tick={{ fontSize: 11 }} />
          <Tooltip contentStyle={tooltipStyle} formatter={v => `${format(Number(v))} TWh`} /><Legend wrapperStyle={{ fontSize: 12 }} />
          <Line dataKey="max" name="Cao nhất (TWh)" stroke="#3b82f6" strokeDasharray="4 4" connectNulls={false} />
          <Line dataKey="mean" name="Trung bình (TWh)" stroke="#f59e0b" strokeWidth={3} connectNulls={false} />
          <Line dataKey="min" name="Thấp nhất (TWh)" stroke="#10b981" strokeDasharray="4 4" connectNulls={false} />
        </LineChart></ResponsiveContainer>
      </ChartFrame>
      <ExportCsv filename="seasonality-api.csv" headers={headers} rows={rows.map(row => [row.month, row.count, row.mean, row.median, row.min, row.max])} />
      <details><summary className="cursor-pointer text-sm text-muted-foreground">Xem thống kê theo tháng</summary><div className="mt-3"><DataTable caption="Thống kê mùa vụ từ API" headers={headers} rows={rows.map(row => [row.month, row.count, format(row.mean), format(row.median), format(row.min), format(row.max)])} /></div></details>
    </div>;
  }}</ApiResult>;
}

export function DistributionApiChart({ points }: { points: DemandPoint[] }) {
  const [bins, setBins] = useState(10);
  return <div className="space-y-4">
    <Selector label="Số khoảng phân bố" value={String(bins)} onChange={value => setBins(Number(value))} options={[5, 10, 15, 20].map(value => ({ value: String(value), label: `${value} khoảng` }))} />
    <ApiResult endpoint="/api/analysis/distribution" params={{ ...rangeParams(points), bins }} parse={parseDistribution}>{result => {
      const rows = result.bins.map(bin => ({ ...bin, range: `${format(bin.start, 1)}–${format(bin.end, 1)}` }));
      if (!result.count) return <p role="status" className="text-sm text-muted-foreground">Không có dữ liệu phân bố trong khoảng đã chọn.</p>;
      return <div className="space-y-4">
        <ChartFrame label="Histogram số tháng theo khoảng tiêu thụ, từ API phân bố">
          <ResponsiveContainer width="100%" height="100%"><BarChart data={rows} margin={{ top: 12, right: 12, bottom: 25, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" /><XAxis dataKey="range" minTickGap={15} tick={{ fontSize: 10 }} label={{ value: "Khoảng tiêu thụ (TWh)", position: "bottom", offset: 8 }} /><YAxis width={45} allowDecimals={false} tick={{ fontSize: 11 }} />
            <Tooltip contentStyle={tooltipStyle} formatter={value => `${value} tháng`} /><Bar dataKey="count" name="Số tháng" fill="#3b82f6" radius={[3, 3, 0, 0]} />
          </BarChart></ResponsiveContainer>
        </ChartFrame>
        <ExportCsv filename="distribution-api.csv" headers={["Từ (TWh)", "Đến (TWh)", "Số tháng"]} rows={rows.map(row => [row.start, row.end, row.count])} />
        <details><summary className="cursor-pointer text-sm text-muted-foreground">Xem các khoảng và số lượng</summary><div className="mt-3"><DataTable caption="Phân bố từ API" headers={["Từ (TWh)", "Đến (TWh)", "Số tháng"]} rows={rows.map(row => [format(row.start, 4), format(row.end, 4), row.count])} /></div></details>
        <p className="text-xs text-muted-foreground">{result.count} tháng. Mỗi khoảng gồm đầu trái, không gồm đầu phải; khoảng cuối gồm cả hai đầu. Đây là histogram, không phải kết quả phân cụm K-Means.</p>
      </div>;
    }}</ApiResult>
  </div>;
}
