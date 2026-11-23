"use client";

import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { mean, movingAverage, seasonalPattern, type DemandPoint } from "@/lib/analysis-data";
import { AnalysisWorkspace, ChartFrame, DataTable, ExportCsv, format, Panel, Selector, Stat } from "./analysis-shared";

const headers = ["Tháng", "Số quan sát", "Trung bình (TWh)", "Thấp nhất (TWh)", "Cao nhất (TWh)"];
const tooltipStyle = { background: "var(--card)", borderColor: "var(--border)", borderRadius: 8, color: "var(--foreground)" };
function TrendView({ points, all }: { points: DemandPoint[]; all: DemandPoint[] }) {
  const [window, setWindow] = useState(6);
  const trend = movingAverage(points, all, window);
  const seasonal = seasonalPattern(points);
  const observed = seasonal.filter(p => p.average !== null);
  const peak = observed.reduce((a, b) => a.average! > b.average! ? a : b);
  const low = observed.reduce((a, b) => a.average! < b.average! ? a : b);
  const average = mean(points.map(p => p.value))!;
  const start = points[0], end = points[points.length - 1];
  const change = points.length > 1 && start.value !== 0 ? (end.value / start.value - 1) * 100 : null;
  return <>
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
      <Stat label="Biến động đầu → cuối kỳ" value={change === null ? "—" : `${change > 0 ? "+" : ""}${format(change)}%`} detail={`${start.month} → ${end.month}; chưa điều chỉnh mùa vụ`} />
      <Stat label="Tháng có TB cao nhất" value={peak.month} detail={`${format(peak.average)} TWh · ${peak.count} quan sát`} />
      <Stat label="Tháng có TB thấp nhất" value={low.month} detail={`${format(low.average)} TWh · ${low.count} quan sát`} />
      <Stat label="Chênh lệch đỉnh / đáy" value={`${format(peak.average! - low.average!)} TWh`} detail={average === 0 ? "Trung bình toàn kỳ bằng 0; không tính tỷ lệ" : `${format((peak.average! - low.average!) / average * 100)}% so với trung bình toàn kỳ`} />
    </div>
    <Panel title="Xu hướng và trung bình trượt" description="Trung bình trượt sử dụng cả các tháng trước khoảng lọc để đủ cửa sổ; không sử dụng dữ liệu tương lai."
      actions={<Selector label="Cửa sổ trung bình trượt" value={String(window)} onChange={v => setWindow(Number(v))} options={[3, 6, 12].map(n => ({ value: String(n), label: `${n} tháng` }))} />}>
      <ChartFrame label="Chuỗi tiêu thụ theo tháng và trung bình trượt">
        <ResponsiveContainer width="100%" height="100%"><LineChart data={trend} margin={{ top: 12, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
          <XAxis dataKey="month" minTickGap={35} tick={{ fontSize: 11 }} /><YAxis width={60} tick={{ fontSize: 11 }} />
          <Tooltip contentStyle={tooltipStyle} formatter={v => `${format(Number(v))} TWh`} /><Legend wrapperStyle={{ fontSize: 12 }} />
          <Line dataKey="value" name="Tiêu thụ (TWh)" stroke="#94a3b8" strokeWidth={1.5} dot={points.length === 1} />
          <Line dataKey="movingAverage" name={`Trung bình ${window} tháng (TWh)`} stroke="#f59e0b" strokeWidth={3} dot={points.length === 1} connectNulls={false} />
        </LineChart></ResponsiveContainer>
      </ChartFrame>
    </Panel>
    <Panel title="Quy luật theo tháng trong năm" description="Gộp các tháng cùng tên trong khoảng lọc. Mỗi tháng có thể có số quan sát khác nhau; đây là mô tả dữ liệu, chưa phải phân rã mùa vụ.">
      <ChartFrame label="Trung bình, mức thấp nhất và cao nhất theo tháng trong năm">
        <ResponsiveContainer width="100%" height="100%"><LineChart data={seasonal} margin={{ top: 12, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" /><XAxis dataKey="month" tick={{ fontSize: 11 }} /><YAxis width={60} tick={{ fontSize: 11 }} />
          <Tooltip contentStyle={tooltipStyle} formatter={v => `${format(Number(v))} TWh`} /><Legend wrapperStyle={{ fontSize: 12 }} />
          <Line dataKey="max" name="Cao nhất (TWh)" stroke="#3b82f6" strokeDasharray="4 4" connectNulls={false} />
          <Line dataKey="average" name="Trung bình (TWh)" stroke="#f59e0b" strokeWidth={3} connectNulls={false} />
          <Line dataKey="min" name="Thấp nhất (TWh)" stroke="#10b981" strokeDasharray="4 4" connectNulls={false} />
        </LineChart></ResponsiveContainer>
      </ChartFrame>
      {points.length < 24 && <p role="status" className="text-sm text-muted-foreground">Khoảng lọc dưới 24 tháng: cần thêm nhiều năm để đánh giá quy luật mùa vụ đáng tin cậy hơn.</p>}
    </Panel>
    <Panel title="Thống kê theo tháng" actions={<ExportCsv filename="seasonality.csv" headers={headers} rows={seasonal.map(p => [p.month, p.count, p.average, p.min, p.max])} />}>
      <DataTable caption="Thống kê mùa vụ" headers={headers} rows={seasonal.map(p => [p.month, p.count, format(p.average), format(p.min), format(p.max)])} />
    </Panel>
    <Panel title="Dữ liệu xu hướng" description="Dấu — nghĩa là chưa đủ lịch sử cho cửa sổ đã chọn."
      actions={<ExportCsv filename={`trend-ma${window}.csv`} headers={["Tháng", "Tiêu thụ (TWh)", `MA${window} (TWh)`]} rows={trend.map(p => [p.month, p.value, p.movingAverage])} />}>
      <DataTable caption="Giá trị xu hướng và trung bình trượt" headers={["Tháng", "Tiêu thụ (TWh)", `MA${window} (TWh)`]} rows={trend.map(p => [p.month, format(p.value), format(p.movingAverage)])} />
    </Panel>
  </>;
}
export function TrendAnalysis() { return <AnalysisWorkspace kind="trend">{(points, all) => <TrendView points={points} all={all} />}</AnalysisWorkspace>; }
