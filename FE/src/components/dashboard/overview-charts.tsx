"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DemandPoint } from "@/lib/analysis-data";
import { parseTrend, rangeParams } from "@/lib/analytics-api";
import { ApiResult } from "@/components/analysis/api-result";
import { ChartFrame, format } from "@/components/analysis/analysis-shared";
import { DistributionApiChart, SeasonalityApiChart } from "@/components/analysis/api-charts";

export function OverviewTrendChart({ points }: { points: DemandPoint[] }) {
  return <ApiResult endpoint="/api/analysis/trend" params={{ ...rangeParams(points), metric: "demand", view: "day" }} parse={parseTrend}>{result => <ChartFrame label="Nhu cầu NEM theo ngày, MW">
    <ResponsiveContainer width="100%" height="100%"><LineChart data={result.records} margin={{ top: 12, right: 12, left: 0, bottom: 8 }}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" /><XAxis dataKey="period" minTickGap={35} tick={{ fontSize: 11 }} /><YAxis width={70} tick={{ fontSize: 11 }} label={{ value: result.unit, position: "insideTopLeft", offset: -5 }} /><Tooltip formatter={value => `${format(Number(value))} ${result.unit}`} /><Legend /><Line type="monotone" dataKey="value" name="Daily demand" stroke="#f59e0b" strokeWidth={2} dot={false} connectNulls={false} /></LineChart></ResponsiveContainer>
  </ChartFrame>}</ApiResult>;
}
export function OverviewSeasonality({ points }: { points: DemandPoint[] }) { return <SeasonalityApiChart points={points} />; }
export function OverviewDistribution({ points }: { points: DemandPoint[] }) { return <DistributionApiChart points={points} />; }
