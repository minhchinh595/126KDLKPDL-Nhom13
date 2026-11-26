"use client";

import { Scatter, ScatterChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { parseCorrelation, parseScatter, rangeParams } from "@/lib/analytics-api";
import type { DemandPoint } from "@/lib/analysis-data";
import { AnalysisWorkspace, ChartFrame, DataTable, ExportCsv, format, Panel, Selector, Stat } from "./analysis-shared";
import { ApiResult } from "./api-result";
import { useState } from "react";

function CorrelationView({ points }: { points: DemandPoint[] }) {
  const [x, setX] = useState("demand"), [y, setY] = useState("price");
  const params = rangeParams(points);
  return <ApiResult endpoint="/api/analysis/correlation" params={params} parse={parseCorrelation}>{result => {
    const metrics = Object.keys(result.metrics);
    if (!metrics.length) return <p role="status">Backend chưa có cặp metric đủ điều kiện tương quan.</p>;
    const selectedX = metrics.includes(x) ? x : metrics[0], selectedY = metrics.includes(y) ? y : metrics.find(metric => metric !== selectedX) ?? metrics[0];
    const count = result.pair_counts[selectedX]?.[selectedY] ?? 0, coefficient = result.matrix[selectedX]?.[selectedY] ?? null;
    const labels = (metric: string) => `${metric} (${result.metrics[metric]?.unit ?? "unit n/a"})`;
    return <div className="space-y-6">
      <Panel title="Chọn metric" description="Các hệ số và scatter được cung cấp trực tiếp bởi NEM Analysis API."><div className="flex flex-wrap gap-4"><Selector label="Trục X" value={selectedX} onChange={setX} options={metrics.filter(metric => metric !== selectedY).map(metric => ({ value: metric, label: labels(metric) }))} /><Selector label="Trục Y" value={selectedY} onChange={setY} options={metrics.filter(metric => metric !== selectedX).map(metric => ({ value: metric, label: labels(metric) }))} /></div></Panel>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4"><Stat label="Pearson r" value={format(coefficient, 6)} detail={coefficient == null ? "Không đủ cặp hoặc không biến thiên" : coefficient > 0 ? "Tương quan thuận" : coefficient < 0 ? "Tương quan nghịch" : "Tương quan tuyến tính bằng 0"} /><Stat label="Số ngày căn chỉnh" value={String(count)} detail={`${labels(selectedX)} ↔ ${labels(selectedY)}`} /><Stat label="Phạm vi ma trận" value={String(result.sample_dates)} detail={result.alignment} /></div>
      <p className="text-xs text-muted-foreground">Diễn giải Pearson r: giá trị gần +1 biểu thị tương quan tuyến tính dương mạnh, gần −1 biểu thị tương quan tuyến tính âm mạnh, còn gần 0 biểu thị tương quan tuyến tính yếu. Tương quan không chứng minh quan hệ nhân quả.</p>
      <Panel title="Scatter theo ngày" description="Điểm và hệ số được tính trên cùng request Backend; tương quan không chứng minh quan hệ nhân quả."><ApiResult endpoint="/api/analysis/scatter" params={{ ...params, x_metric: selectedX, y_metric: selectedY }} parse={parseScatter}>{scatter => !scatter.points.length ? <p role="status">Không có cặp observation hợp lệ.</p> : <ChartFrame label={`Scatter ${selectedX} và ${selectedY}`}><ResponsiveContainer width="100%" height="100%"><ScatterChart><CartesianGrid strokeDasharray="3 3" /><XAxis type="number" dataKey="x" name={labels(selectedX)} /><YAxis type="number" dataKey="y" name={labels(selectedY)} /><Tooltip cursor={{ strokeDasharray: "3 3" }} /><Scatter data={scatter.points} name="Ngày NEM" fill="#3b82f6" /></ScatterChart></ResponsiveContainer></ChartFrame>}</ApiResult></Panel>
      <Panel title="Ma trận tương quan" description="Unit được giữ riêng theo metric; không quy đổi đơn vị ngầm."><DataTable caption="Ma trận Pearson NEM" headers={["Metric", ...metrics.map(labels)]} rows={metrics.map(row => [labels(row), ...metrics.map(column => `${format(result.matrix[row]?.[column] ?? null, 5)} (${result.pair_counts[row]?.[column] ?? 0})`)])} /><ExportCsv filename="nem-correlation-matrix.csv" headers={["Metric X", "Metric Y", "Pearson r", "Pair count"]} rows={metrics.flatMap(row => metrics.map(column => [row, column, result.matrix[row]?.[column] ?? null, result.pair_counts[row]?.[column] ?? 0]))} /></Panel>
    </div>;
  }}</ApiResult>;
}
export function CorrelationAnalysis() { return <AnalysisWorkspace kind="correlation">{points => <CorrelationView points={points} />}</AnalysisWorkspace>; }
