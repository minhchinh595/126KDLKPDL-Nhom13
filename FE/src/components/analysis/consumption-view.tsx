"use client";

import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { aggregateDemand, mean, type DemandPoint, type Granularity } from "@/lib/analysis-data";
import { AnalysisWorkspace, ChartFrame, DataTable, ExportCsv, format, Panel, Selector, Stat } from "./analysis-shared";

const headers = ["Kỳ", "Số tháng", "Tổng (TWh)", "TB/tháng (TWh)", "Cùng kỳ (TWh)", "YoY (%)"];
function ConsumptionView({ points, all }: { points: DemandPoint[]; all: DemandPoint[] }) {
  const [group, setGroup] = useState<Granularity>("month");
  const data = aggregateDemand(points, all, group);
  const total = points.reduce((sum, p) => sum + p.value, 0);
  const peak = points.reduce((a, b) => a.value > b.value ? a : b);
  const low = points.reduce((a, b) => a.value < b.value ? a : b);
  return <>
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
      <Stat label="Tổng tiêu thụ" value={`${format(total)} TWh`} detail={`${points.length} tháng trong khoảng đã chọn`} />
      <Stat label="Trung bình tháng" value={`${format(mean(points.map(p => p.value)))} TWh`} detail="Tính trên các tháng có dữ liệu" />
      <Stat label="Tháng cao nhất" value={`${format(peak.value)} TWh`} detail={peak.month} />
      <Stat label="Tháng thấp nhất" value={`${format(low.value)} TWh`} detail={low.month} />
    </div>
    <Panel title="Tiêu thụ và so sánh cùng kỳ" description="Tổng điện năng theo kỳ. Đường nét đứt biểu diễn tổng của đúng các tháng tương ứng ở năm trước."
      actions={<Selector label="Gộp dữ liệu" value={group} onChange={v => setGroup(v as Granularity)} options={[{ value: "month", label: "Theo tháng" }, { value: "quarter", label: "Theo quý" }, { value: "year", label: "Theo năm" }]} />}>
      <ChartFrame label="Biểu đồ cột tổng tiêu thụ và đường so sánh cùng kỳ năm trước; chi tiết trong bảng bên dưới">
        <ResponsiveContainer width="100%" height="100%"><ComposedChart data={data} margin={{ top: 12, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
          <XAxis dataKey="period" minTickGap={35} tick={{ fontSize: 11 }} />
          <YAxis width={65} tick={{ fontSize: 11 }} label={{ value: "TWh", position: "insideTopLeft", offset: -5 }} />
          <Tooltip contentStyle={{ background: "var(--card)", borderColor: "var(--border)", borderRadius: 8, color: "var(--foreground)" }} formatter={v => `${format(Number(v))} TWh`} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="total" name="Tiêu thụ" fill="#f59e0b" radius={[3, 3, 0, 0]} maxBarSize={48} />
          <Line dataKey="previous" name="Cùng kỳ năm trước" stroke="#3b82f6" strokeDasharray="5 4" strokeWidth={2} dot={false} connectNulls={false} />
        </ComposedChart></ResponsiveContainer>
      </ChartFrame>
    </Panel>
    <Panel title="Chi tiết tiêu thụ" description="Kỳ chưa đủ tháng vẫn hiển thị tổng thực có. YoY chỉ tính khi có đủ tháng đối chiếu; dấu — là chưa đủ dữ liệu."
      actions={<ExportCsv filename={`consumption-${group}.csv`} headers={headers} rows={data.map(p => [p.period, p.count, p.total, p.average, p.previous, p.growth])} />}>
      <DataTable caption="Chi tiết tiêu thụ trong khoảng đã lọc" headers={headers} rows={data.map(p => [p.period, `${p.count} tháng`, format(p.total), format(p.average), format(p.previous), p.growth === null ? "—" : `${p.growth > 0 ? "+" : ""}${format(p.growth)}%`])} />
    </Panel>
  </>;
}
export function ConsumptionAnalysis() {
  return <AnalysisWorkspace kind="consumption">{(points, all) => <ConsumptionView points={points} all={all} />}</AnalysisWorkspace>;
}
