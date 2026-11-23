"use client";

import { Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartFrame, format } from "@/components/analysis/analysis-shared";
import { monthlyChanges, seasonalPattern, summarizeDemand, type DemandPoint } from "@/lib/analysis-data";

const tooltipStyle = { background: "var(--card)", borderColor: "var(--border)", borderRadius: 8, color: "var(--foreground)" };
export function OverviewTrendChart({ points, all, compare }: { points: DemandPoint[]; all: DemandPoint[]; compare: boolean }) {
  return <ChartFrame label="Tiêu thụ điện theo tháng và cùng kỳ năm trước; số liệu trong bảng chi tiết">
    <ResponsiveContainer width="100%" height="100%"><ComposedChart data={monthlyChanges(points, all)} margin={{ top: 15, right: 12, left: 0, bottom: 8 }}>
      <defs><linearGradient id="overview-demand-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f59e0b" stopOpacity={0.35} /><stop offset="100%" stopColor="#f59e0b" stopOpacity={0.03} /></linearGradient></defs>
      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
      <XAxis dataKey="month" minTickGap={35} tick={{ fontSize: 11 }} /><YAxis width={60} tick={{ fontSize: 11 }} label={{ value: "TWh", position: "insideTopLeft", offset: -5 }} />
      <Tooltip contentStyle={tooltipStyle} formatter={value => `${format(Number(value))} TWh`} /><Legend wrapperStyle={{ fontSize: 12 }} />
      <Area type="monotone" dataKey="value" name="Tiêu thụ" stroke="#f59e0b" strokeWidth={2} fill="url(#overview-demand-fill)" dot={points.length === 1} />
      {compare && <Line type="monotone" dataKey="previous" name="Cùng kỳ năm trước" stroke="#3b82f6" strokeWidth={2} strokeDasharray="5 4" dot={points.length === 1} connectNulls={false} />}
    </ComposedChart></ResponsiveContainer>
  </ChartFrame>;
}

export function OverviewSeasonality({ points }: { points: DemandPoint[] }) {
  const data = seasonalPattern(points);
  return <>
    <ChartFrame label="Tiêu thụ trung bình theo tháng trong năm">
      <ResponsiveContainer width="100%" height="100%"><BarChart data={data} margin={{ top: 10, right: 8, left: -10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" /><XAxis dataKey="month" tick={{ fontSize: 11 }} /><YAxis width={55} tick={{ fontSize: 11 }} />
        <Tooltip contentStyle={tooltipStyle} formatter={value => `${format(Number(value))} TWh`} />
        <Bar dataKey="average" name="Trung bình tháng" fill="#3b82f6" radius={[4, 4, 0, 0]} maxBarSize={36} />
      </BarChart></ResponsiveContainer>
    </ChartFrame>
    <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Xem số liệu biểu đồ</summary><ul className="mt-2 grid grid-cols-2 gap-2">{data.map(p => <li key={p.month}>{p.month}: {format(p.average)} TWh ({p.count} quan sát)</li>)}</ul></details>
  </>;
}

export function OverviewDistribution({ points }: { points: DemandPoint[] }) {
  const { levels } = summarizeDemand(points, points);
  return <>
    <ChartFrame label="Phân bố số tháng theo ba ngưỡng tiêu thụ; số liệu trong chú giải bên dưới">
      <ResponsiveContainer width="100%" height="100%"><PieChart>
        <Pie data={levels.filter(p => p.count > 0)} dataKey="count" nameKey="label" cx="50%" cy="50%" innerRadius="55%" outerRadius="80%" paddingAngle={3}>
          {levels.filter(p => p.count > 0).map(p => <Cell key={p.key} fill={p.color} />)}
        </Pie>
        <Tooltip contentStyle={tooltipStyle} formatter={value => `${value} tháng`} />
      </PieChart></ResponsiveContainer>
    </ChartFrame>
    <ul className="space-y-2">{levels.map(p => <li key={p.key} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border p-2 text-xs">
      <span className="flex items-center gap-2"><span className="size-2.5 rounded-full" style={{ backgroundColor: p.color }} />{p.label} · {p.range}</span><span className="font-medium tabular-nums">{p.count} tháng ({format(p.percentage, 1)}%)</span>
    </li>)}</ul>
  </>;
}
