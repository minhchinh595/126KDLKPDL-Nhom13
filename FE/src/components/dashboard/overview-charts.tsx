"use client";

import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartFrame, format } from "@/components/analysis/analysis-shared";
import { ApiResult } from "@/components/analysis/api-result";
import { SeasonalityApiChart, DistributionApiChart } from "@/components/analysis/api-charts";
import { monthlyChanges, type DemandPoint } from "@/lib/analysis-data";
import { parseTrend, rangeParams } from "@/lib/analytics-api";

export function OverviewTrendChart({ points, all, compare }: { points: DemandPoint[]; all: DemandPoint[]; compare: boolean }) {
  return <ApiResult endpoint="/api/analysis/trend" params={{ ...rangeParams(points), window_months: 12 }} parse={parseTrend}>{result => <ChartFrame label="Tiêu thụ và trung bình trượt từ API xu hướng, so sánh với dữ liệu cùng kỳ">
    <ResponsiveContainer width="100%" height="100%"><ComposedChart data={monthlyChanges(result.records, all)} margin={{ top: 15, right: 12, left: 0, bottom: 8 }}>
      <defs><linearGradient id="overview-demand-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f59e0b" stopOpacity={0.35} /><stop offset="100%" stopColor="#f59e0b" stopOpacity={0.03} /></linearGradient></defs>
      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
      <XAxis dataKey="month" minTickGap={35} tick={{ fontSize: 11 }} /><YAxis width={60} tick={{ fontSize: 11 }} label={{ value: "TWh", position: "insideTopLeft", offset: -5 }} />
      <Tooltip contentStyle={{ background: "var(--card)", borderColor: "var(--border)", color: "var(--foreground)" }} formatter={value => `${format(Number(value))} TWh`} /><Legend wrapperStyle={{ fontSize: 12 }} />
      <Area type="monotone" dataKey="value" name="Tiêu thụ" stroke="#f59e0b" strokeWidth={2} fill="url(#overview-demand-fill)" dot={points.length === 1} />
      <Line type="monotone" dataKey="trend" name="Trung bình trượt 12 tháng" stroke="#8b5cf6" strokeWidth={2} dot={false} connectNulls={false} />
      {compare && <Line type="monotone" dataKey="previous" name="Cùng kỳ năm trước" stroke="#3b82f6" strokeWidth={2} strokeDasharray="5 4" dot={points.length === 1} connectNulls={false} />}
    </ComposedChart></ResponsiveContainer>
  </ChartFrame>}</ApiResult>;
}
export function OverviewSeasonality({ points }: { points: DemandPoint[] }) { return <SeasonalityApiChart points={points} />; }
export function OverviewDistribution({ points }: { points: DemandPoint[] }) { return <DistributionApiChart points={points} />; }
