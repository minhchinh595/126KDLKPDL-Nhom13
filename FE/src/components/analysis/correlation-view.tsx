"use client";

import { useState } from "react";
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { pairedObservations, pearson, spearman, VARIABLES, type DemandPoint, type Variable } from "@/lib/analysis-data";
import { AnalysisWorkspace, ChartFrame, DataTable, ExportCsv, format, Panel, Selector, Stat } from "./analysis-shared";

const options = Object.entries(VARIABLES).map(([value, info]) => ({ value, label: `${info.label} (${info.unit})` }));
function strength(r: number | null) {
  if (r === null) return "Chưa đủ dữ liệu hoặc biến không thay đổi";
  const abs = Math.abs(r);
  if (abs < 0.2) return "Liên hệ tuyến tính rất yếu";
  return `Tương quan ${r < 0 ? "nghịch" : "thuận"} ${abs >= 0.8 ? "rất mạnh" : abs >= 0.6 ? "mạnh" : abs >= 0.4 ? "vừa" : "yếu"} (mức tham khảo)`;
}
function CorrelationView({ points, all }: { points: DemandPoint[]; all: DemandPoint[] }) {
  const [x, setX] = useState<Variable>("previousMonth");
  const [y, setY] = useState<Variable>("demand");
  const data = pairedObservations(points, all, x, y);
  const r = pearson(data.map(p => p.x), data.map(p => p.y));
  const rho = spearman(data.map(p => p.x), data.map(p => p.y));
  const variables = Object.keys(VARIABLES) as Variable[];
  const xl = `${VARIABLES[x].label} (${VARIABLES[x].unit})`, yl = `${VARIABLES[y].label} (${VARIABLES[y].unit})`;
  const headers = ["Tháng", xl, yl];
  return <>
    <Panel title="Chọn biến phân tích" description="Các biến trễ lấy từ lịch sử đầy đủ trước khi lọc. Bản ghi thiếu một trong hai giá trị được loại khỏi từng cặp.">
      <div className="flex flex-wrap gap-4">
        <Selector label="Biến trục X" value={x} onChange={v => setX(v as Variable)} options={options.filter(o => o.value !== y)} />
        <Selector label="Biến trục Y" value={y} onChange={v => setY(v as Variable)} options={options.filter(o => o.value !== x)} />
      </div>
    </Panel>
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <Stat label="Pearson r" value={format(r, 3)} detail={strength(r)} />
      <Stat label="Spearman ρ" value={format(rho, 3)} detail="Tương quan theo thứ hạng; hạng trùng lấy trung bình" />
      <Stat label="Số cặp hợp lệ" value={String(data.length)} detail={`${points.length - data.length} bản ghi thiếu giá trị đối chiếu`} />
    </div>
    <Panel title="Biểu đồ phân tán" description={`X: ${xl} · Y: ${yl}`}>
      {data.length ? <ChartFrame label={`Biểu đồ phân tán ${xl} và ${yl}; từng cặp có trong bảng bên dưới`}>
        <ResponsiveContainer width="100%" height="100%"><ScatterChart margin={{ top: 20, right: 20, bottom: 28, left: 15 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis type="number" dataKey="x" name={VARIABLES[x].label} unit={` ${VARIABLES[x].unit}`} domain={['auto', 'auto']} tick={{ fontSize: 11 }} label={{ value: `X (${VARIABLES[x].unit})`, position: "bottom", offset: 10 }} />
          <YAxis type="number" dataKey="y" name={VARIABLES[y].label} unit={` ${VARIABLES[y].unit}`} domain={['auto', 'auto']} width={70} tick={{ fontSize: 11 }} label={{ value: `Y (${VARIABLES[y].unit})`, angle: -90, position: "insideLeft", offset: -4 }} />
          <Tooltip cursor={{ strokeDasharray: "3 3" }} content={({ active, payload }) => {
            const point = payload?.[0]?.payload as { month: string; x: number; y: number } | undefined;
            return active && point ? <div className="rounded-lg border border-border bg-card p-3 text-xs shadow-md space-y-1"><p className="font-semibold">Tháng {point.month}</p><p>{VARIABLES[x].label}: {format(point.x)} {VARIABLES[x].unit}</p><p>{VARIABLES[y].label}: {format(point.y)} {VARIABLES[y].unit}</p></div> : null;
          }} />
          <Scatter data={data} name="Quan sát theo tháng" fill="#3b82f6" fillOpacity={0.7} />
        </ScatterChart></ResponsiveContainer>
      </ChartFrame> : <p role="status" className="py-12 text-center text-muted-foreground">Không có cặp dữ liệu hợp lệ. Hãy mở rộng khoảng thời gian hoặc chọn biến khác.</p>}
      <p className="text-sm text-muted-foreground">{r === null ? "Cần ít nhất 3 cặp hợp lệ và cả hai biến phải có độ biến thiên để tính hệ số." : strength(r) + "."} Tương quan không chứng minh quan hệ nhân quả. Xu hướng tăng theo năm có thể làm hệ số giữa các biến trễ cao hơn. Tháng trong năm là biến chu kỳ; Pearson chỉ mô tả liên hệ tuyến tính, không phản ánh đầy đủ mùa vụ.</p>
    </Panel>
    <Panel title="Ma trận tương quan Pearson" description="Mỗi ô dùng các cặp hợp lệ riêng; số trong ngoặc là số cặp. Dấu —: dưới 3 cặp hoặc biến không đổi.">
      <DataTable caption="Ma trận hệ số Pearson" headers={["Biến", ...variables.map(v => VARIABLES[v].label)]} rows={variables.map(a => [VARIABLES[a].label, ...variables.map(b => {
        const pairs = pairedObservations(points, all, a, b);
        const value = pearson(pairs.map(p => p.x), pairs.map(p => p.y));
        return <span key={b} className={`rounded px-2 py-1 ${value === null ? "bg-muted" : value >= 0 ? "bg-blue-500/10 text-blue-700 dark:text-blue-300" : "bg-amber-500/10 text-amber-700 dark:text-amber-300"}`}>{format(value, 3)} ({pairs.length})</span>;
      })])} />
    </Panel>
    <Panel title="Các cặp quan sát" actions={<ExportCsv filename={`correlation-${x}-${y}.csv`} headers={headers} rows={data.map(p => [p.month, p.x, p.y])} />}>
      {data.length ? <DataTable caption="Các cặp dữ liệu dùng tính tương quan" headers={headers} rows={data.map(p => [p.month, format(p.x), format(p.y)])} /> : <p className="text-sm text-muted-foreground">Không có quan sát để hiển thị.</p>}
    </Panel>
  </>;
}
export function CorrelationAnalysis() { return <AnalysisWorkspace kind="correlation">{(points, all) => <CorrelationView points={points} all={all} />}</AnalysisWorkspace>; }
