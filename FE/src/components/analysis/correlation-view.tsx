"use client";

import { useState } from "react";
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { pairedObservations, type DemandPoint, type Variable } from "@/lib/analysis-data";
import { CORRELATION_FEATURES, parseCorrelation, rangeParams, type CorrelationFeature } from "@/lib/analytics-api";
import { AnalysisWorkspace, ChartFrame, DataTable, ExportCsv, format, Panel, Selector, Stat } from "./analysis-shared";
import { ApiResult } from "./api-result";

const labels: Record<CorrelationFeature, string> = { demand: "Tiêu thụ hiện tại", previous_month: "Tiêu thụ tháng trước", previous_year: "Tiêu thụ cùng kỳ năm trước" };
const variables: Record<CorrelationFeature, Variable> = { demand: "demand", previous_month: "previousMonth", previous_year: "previousYear" };
const options = CORRELATION_FEATURES.map(value => ({ value, label: labels[value] }));
function CorrelationView({ points }: { points: DemandPoint[] }) {
  const [x, setX] = useState<CorrelationFeature>("previous_month");
  const [y, setY] = useState<CorrelationFeature>("demand");
  // The public API builds lag variables within the filtered range. Match that scope for scatter points.
  const observations = pairedObservations(points, points, variables[x], variables[y]);
  const headers = ["Tháng", `${labels[x]} (TWh)`, `${labels[y]} (TWh)`];
  return <>
    <Panel title="Chọn biến phân tích" description="API cung cấp Pearson cho ba biến tiêu thụ. Các biến trễ chỉ dùng lịch sử nằm trong khoảng lọc.">
      <div className="flex flex-wrap gap-4">
        <Selector label="Biến trục X" value={x} onChange={value => setX(value as CorrelationFeature)} options={options.filter(option => option.value !== y)} />
        <Selector label="Biến trục Y" value={y} onChange={value => setY(value as CorrelationFeature)} options={options.filter(option => option.value !== x)} />
      </div>
    </Panel>
    <ApiResult endpoint="/api/analysis/correlation" params={rangeParams(points)} parse={parseCorrelation}>{result => {
      const r = result.matrix[x][y], count = result.pair_counts[x][y];
      const matching = count === observations.length;
      return <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Stat label="Pearson r từ API" value={format(r, 6)} detail={r === null ? "Chưa đủ cặp hoặc biến không thay đổi" : r > 0 ? "Tương quan thuận" : r < 0 ? "Tương quan nghịch" : "Không có liên hệ tuyến tính"} />
          <Stat label="Số cặp hợp lệ từ API" value={String(count)} detail={`${labels[x]} ↔ ${labels[y]}`} />
          <Stat label="Phương pháp" value="Pearson" detail="Backend chưa cung cấp Spearman hoặc biến tháng trong năm" />
        </div>
        <Panel title="Biểu đồ phân tán" description={`X: ${labels[x]} · Y: ${labels[y]} · TWh`}>
          {!matching ? <p role="alert" className="text-sm text-destructive">Số cặp giữa dữ liệu nguồn và kết quả phân tích không khớp. Hãy bấm Tải lại từ API để đồng bộ dữ liệu.</p> : !observations.length ? <p role="status" className="py-8 text-center text-muted-foreground">Không có cặp dữ liệu hợp lệ trong khoảng lọc.</p> : <ChartFrame label={`Biểu đồ phân tán ${labels[x]} và ${labels[y]}`}>
            <ResponsiveContainer width="100%" height="100%"><ScatterChart margin={{ top: 20, right: 20, bottom: 28, left: 15 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis type="number" dataKey="x" domain={["auto", "auto"]} tick={{ fontSize: 11 }} label={{ value: "X (TWh)", position: "bottom", offset: 10 }} />
              <YAxis type="number" dataKey="y" domain={["auto", "auto"]} width={60} tick={{ fontSize: 11 }} label={{ value: "Y (TWh)", angle: -90, position: "insideLeft" }} />
              <Tooltip content={({ active, payload }) => {
                const point = payload?.[0]?.payload as { month: string; x: number; y: number } | undefined;
                return active && point ? <div className="rounded-lg border border-border bg-card p-3 text-xs space-y-1"><p className="font-semibold">Tháng {point.month}</p><p>{labels[x]}: {format(point.x)} TWh</p><p>{labels[y]}: {format(point.y)} TWh</p></div> : null;
              }} />
              <Scatter data={observations} name="Các cặp từ dữ liệu API" fill="#3b82f6" fillOpacity={0.7} />
            </ScatterChart></ResponsiveContainer>
          </ChartFrame>}
          <p className="text-sm text-muted-foreground">Hệ số được lấy từ API phân tích. Điểm scatter được ghép từ dữ liệu tiêu thụ vì API chưa trả danh sách cặp. Tương quan không chứng minh quan hệ nhân quả.</p>
        </Panel>
        <Panel title="Ma trận Pearson từ API" description="Số trong ngoặc là số cặp hợp lệ; dấu — nghĩa là chưa tính được hệ số.">
          <DataTable caption="Ma trận tương quan từ API" headers={["Biến", ...result.features.map(feature => labels[feature])]} rows={result.features.map(a => [labels[a], ...result.features.map(b => `${format(result.matrix[a][b], 6)} (${result.pair_counts[a][b]})`)])} />
          <ExportCsv filename="correlation-matrix-api.csv" headers={["Biến X", "Biến Y", "Pearson r", "Số cặp"]} rows={result.features.flatMap(a => result.features.map(b => [labels[a], labels[b], result.matrix[a][b], result.pair_counts[a][b]]))} />
        </Panel>
        {matching && <Panel title="Các cặp quan sát" actions={<ExportCsv filename={`correlation-${x}-${y}.csv`} headers={headers} rows={observations.map(point => [point.month, point.x, point.y])} />}>
          <DataTable caption="Các cặp dữ liệu dùng vẽ scatter" headers={headers} rows={observations.map(point => [point.month, format(point.x), format(point.y)])} />
        </Panel>}
      </div>;
    }}</ApiResult>
  </>;
}
export function CorrelationAnalysis() { return <AnalysisWorkspace kind="correlation">{points => <CorrelationView points={points} />}</AnalysisWorkspace>; }
