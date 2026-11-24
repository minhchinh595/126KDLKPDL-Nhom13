"use client";

import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DemandPoint } from "@/lib/analysis-data";
import { parseTrend, rangeParams } from "@/lib/analytics-api";
import { AnalysisWorkspace, ChartFrame, DataTable, ExportCsv, format, Panel, Selector, Stat } from "./analysis-shared";
import { ApiResult } from "./api-result";
import { SeasonalityApiChart } from "./api-charts";

function TrendView({ points }: { points: DemandPoint[] }) {
  const [window, setWindow] = useState(6);
  return <>
    <Panel title="Xu hướng và trung bình trượt" description="Kết quả tính bởi Analysis Service. Cửa sổ chỉ dùng các tháng trong khoảng lọc; các tháng đầu chưa đủ lịch sử sẽ có dấu —."
      actions={<Selector label="Cửa sổ trung bình trượt" value={String(window)} onChange={value => setWindow(Number(value))} options={[3, 6, 12].map(value => ({ value: String(value), label: `${value} tháng` }))} />}>
      <ApiResult endpoint="/api/analysis/trend" params={{ ...rangeParams(points), window_months: window }} parse={parseTrend}>{result => {
        const latest = result.records.at(-1);
        const first = result.records[0];
        const change = first && latest && first.value !== 0 && result.records.length > 1 ? (latest.value / first.value - 1) * 100 : null;
        if (!latest) return <p role="status">Không có kết quả xu hướng trong khoảng đã chọn.</p>;
        const headers = ["Tháng", "Tiêu thụ (TWh)", `MA${result.window_months} (TWh)`];
        return <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Stat label="Tiêu thụ cuối kỳ" value={`${format(latest.value)} TWh`} detail={latest.month} />
            <Stat label={`Trung bình trượt ${result.window_months} tháng`} value={format(latest.trend)} detail={latest.trend === null ? "Chưa đủ lịch sử trong khoảng lọc" : "TWh · trailing rolling mean"} />
            <Stat label="Biến động đầu → cuối kỳ" value={change === null ? "—" : `${change > 0 ? "+" : ""}${format(change)}%`} detail="Từ chuỗi API; chưa điều chỉnh mùa vụ" />
          </div>
          <ChartFrame label="Chuỗi tiêu thụ và trung bình trượt từ API xu hướng">
            <ResponsiveContainer width="100%" height="100%"><LineChart data={result.records} margin={{ top: 12, right: 12, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" /><XAxis dataKey="month" minTickGap={35} tick={{ fontSize: 11 }} /><YAxis width={60} tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "var(--card)", borderColor: "var(--border)", color: "var(--foreground)" }} formatter={value => `${format(Number(value))} TWh`} /><Legend wrapperStyle={{ fontSize: 12 }} />
              <Line dataKey="value" name="Tiêu thụ (TWh)" stroke="#94a3b8" strokeWidth={1.5} dot={result.records.length === 1} />
              <Line dataKey="trend" name={`Trung bình ${result.window_months} tháng (TWh)`} stroke="#f59e0b" strokeWidth={3} dot={result.records.length === 1} connectNulls={false} />
            </LineChart></ResponsiveContainer>
          </ChartFrame>
          <ExportCsv filename={`trend-ma${result.window_months}-api.csv`} headers={headers} rows={result.records.map(row => [row.month, row.value, row.trend])} />
          <DataTable caption="Kết quả xu hướng từ API" headers={headers} rows={result.records.map(row => [row.month, format(row.value), format(row.trend)])} />
        </div>;
      }}</ApiResult>
    </Panel>
    <Panel title="Quy luật theo tháng trong năm" description="Trung bình, trung vị và khoảng tiêu thụ được trả về từ API mùa vụ.">
      <SeasonalityApiChart points={points} />
      {points.length < 24 && <p className="text-xs text-muted-foreground">Dưới 24 tháng dữ liệu: chưa đủ nhiều chu kỳ để kết luận về mùa vụ.</p>}
    </Panel>
  </>;
}
export function TrendAnalysis() { return <AnalysisWorkspace kind="trend">{points => <TrendView points={points} />}</AnalysisWorkspace>; }
