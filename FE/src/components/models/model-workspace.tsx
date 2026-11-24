"use client";
import { useState } from "react";
import { Shapes, Sparkles, ChartNoAxesCombined } from "lucide-react";
import { PageHeading } from "@/components/shared/page-heading";
import { StatusBadge } from "@/components/shared/status-badge";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AppLayout } from "@/components/layout/app-layout";
import { useSession } from "@/components/auth/session-provider";
import { useDemandData } from "@/components/dashboard/demand-data-provider";
import { canManage, gatewayRequest, modelActionPath, query, type ModelKind, type ModelRun, type PageResult } from "@/lib/gateway";
import Link from "next/link";
import { Panel, Stat, ChartFrame, DataTable, ExportCsv, format } from "@/components/analysis/analysis-shared";
import { QueryState, useGatewayQuery, Pagination } from "@/components/shared/gateway-resource";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const titles: Record<ModelKind, string> = { clustering: "Phân cụm tiêu thụ", prediction: "Dự báo nhu cầu", classification: "Phân loại tiêu thụ" };
const colors = ["#f59e0b", "#3b82f6", "#10b981", "#8b5cf6", "#ef4444", "#06b6d4", "#ec4899", "#64748b"];
const record = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const list = (value: unknown): Record<string, unknown>[] => Array.isArray(value) ? value.map(record) : [];
const numeric = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : null;
const text = (value: unknown) => typeof value === "string" ? value : typeof value === "number" ? String(value) : "—";

export function ForecastPreview() {
  const result = useGatewayQuery<ModelRun>("/api/prediction/latest");
  return <QueryState resource={result} empty="Chưa có dự báo. Admin có thể huấn luyện và chạy mô hình tại trang Dự báo.">{run => <ModelResult run={run} />}</QueryState>;
}
export function ModelResult({ run }: { run: ModelRun }) {
  const m = run.metrics ?? {};
  const { state } = useDemandData();
  const stage = text(m.stage ?? run.parameters?.stage);
  const holdout = record(m.holdout_metrics);
  const groups = list(m.cluster_summaries), assignments = list(m.assignments), probabilities = list(m.probabilities);
  const forecastMonth = typeof m.forecast_month === "string" ? m.forecast_month : null;
  const forecastValue = numeric(m.predicted_demand);
  const history = state.status === "success" ? state.data.records.slice(-12).map(point => ({ month: point.month, actual: point.value, forecast: null as number | null })) : [];
  const series = forecastMonth && forecastValue !== null ? [...history, { month: forecastMonth, actual: undefined, forecast: forecastValue }] : history;
  return <div className="space-y-4">
    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground"><span>Lượt #{run.id}</span><StatusBadge status={run.status} /><span>{stage === "training" ? "Huấn luyện" : "Kết quả chạy"}</span><span>{new Date(run.created_at).toLocaleString("vi-VN")}</span></div>
    {run.error_message && <p role="alert" className="text-sm text-destructive">{run.error_message}</p>}
    {run.status !== "completed" && !run.error_message && <p role="status">Lượt này chưa có kết quả hoàn tất.</p>}
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <Stat label="Mô hình" value={text(m.model_name ?? m.method)} detail={titles[run.model_type]} />
      <Stat label="Huấn luyện đến tháng" value={text(m.trained_through_month)} detail="Theo kết quả Gateway" />
      {run.model_type === "clustering" ? <Stat label="Số cụm được chọn" value={text(m.selected_k)} detail={`Silhouette: ${format(numeric(m.silhouette_score), 6)}`} /> : run.model_type === "prediction" ? <Stat label="Dự báo" value={forecastValue === null ? "—" : `${format(forecastValue)} TWh`} detail={forecastMonth ?? "Chạy mô hình sau khi huấn luyện"} /> : <Stat label="Mức dự báo" value={text(m.predicted_level_name)} detail={forecastMonth ?? "Chạy mô hình sau khi huấn luyện"} />}
    </div>
    {groups.length > 0 && <>
      <ChartFrame label="Số tháng theo cụm K-Means từ Gateway"><ResponsiveContainer width="100%" height="100%"><BarChart data={groups}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="label" tick={{ fontSize: 11 }} /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="month_count" name="Số tháng">{groups.map((group, index) => <Cell key={text(group.cluster_id)} fill={colors[index % colors.length]} />)}</Bar></BarChart></ResponsiveContainer></ChartFrame>
      <DataTable caption="Thống kê các cụm" headers={["Cụm", "Số tháng", "TB (TWh)", "Min", "Max"]} rows={groups.map(group => [text(group.label), text(group.month_count), format(numeric(group.mean_demand)), format(numeric(group.min_demand)), format(numeric(group.max_demand))])} />
    </>}
    {assignments.length > 0 && <>
      <ExportCsv filename={`clustering-run-${run.id}.csv`} headers={["Tháng", "Cụm", "Tiêu thụ (TWh)"]} rows={assignments.map(item => [text(item.month), text(item.cluster_label), numeric(item.demand)])} />
      <DataTable caption="Kết quả phân cụm theo tháng" headers={["Tháng", "Cụm", "Tiêu thụ (TWh)"]} rows={assignments.map(item => [text(item.month), text(item.cluster_label), format(numeric(item.demand))])} />
    </>}
    {forecastMonth && forecastValue !== null && <>
      <ChartFrame label="Dữ liệu thực tế và dự báo một tháng từ Gateway"><ResponsiveContainer width="100%" height="100%"><LineChart data={series}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="month" minTickGap={30} tick={{ fontSize: 11 }} /><YAxis /><Tooltip /><Legend /><Line dataKey="actual" name="Thực tế (TWh)" stroke="#3b82f6" dot={false} /><Line dataKey="forecast" name="Dự báo (TWh)" stroke="#8b5cf6" dot={{ r: 6 }} connectNulls={false} /></LineChart></ResponsiveContainer></ChartFrame>
      <ExportCsv filename={`prediction-run-${run.id}.csv`} headers={["Tháng", "Dự báo (TWh)"]} rows={[[forecastMonth, forecastValue]]} />
    </>}
    {probabilities.length > 0 && <>
      <ChartFrame label="Xác suất các mức tiêu thụ từ mô hình phân loại"><ResponsiveContainer width="100%" height="100%"><BarChart data={probabilities}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="label_name" tick={{ fontSize: 11 }} /><YAxis domain={[0, 1]} /><Tooltip /><Bar dataKey="probability" name="Xác suất" fill="#10b981" /></BarChart></ResponsiveContainer></ChartFrame>
      <DataTable caption="Xác suất phân loại" headers={["Mức", "Xác suất"]} rows={probabilities.map(item => [text(item.label_name), `${format((numeric(item.probability) ?? 0) * 100)}%`])} />
      <ExportCsv filename={`classification-run-${run.id}.csv`} headers={["Tháng", "Mức", "Xác suất"]} rows={probabilities.map(item => [forecastMonth, text(item.label_name), numeric(item.probability)])} />
    </>}
    {Object.keys(holdout).length > 0 && <Panel title="Đánh giá trên tập kiểm tra">
      <DataTable caption="Chỉ số đánh giá mô hình" headers={["Chỉ số", "Giá trị"]} rows={Object.entries(holdout).filter(([, value]) => typeof value === "number").map(([key, value]) => [key, format(numeric(value), 4)])} />
      {Object.keys(record(holdout.per_class)).length > 0 && <DataTable caption="Đánh giá từng lớp" headers={["Lớp", "Precision", "Recall", "Support"]} rows={Object.entries(record(holdout.per_class)).map(([label, values]) => [label, format(numeric(record(values).precision), 4), format(numeric(record(values).recall), 4), text(record(values).support)])} />}
      {Array.isArray(record(holdout.confusion_matrix).matrix) && <DataTable caption="Ma trận nhầm lẫn" headers={["Thực tế / Dự đoán", ...(Array.isArray(record(holdout.confusion_matrix).label_names) ? record(holdout.confusion_matrix).label_names as string[] : [])]} rows={(record(holdout.confusion_matrix).matrix as number[][]).map((row, index) => [text((record(holdout.confusion_matrix).label_names as string[] | undefined)?.[index]), ...row])} />}
    </Panel>}
    {list(m.candidate_scores).length > 0 && <DataTable caption="Đánh giá lựa chọn K" headers={["K", "Silhouette", "Inertia"]} rows={list(m.candidate_scores).map(item => [text(item.k), format(numeric(item.silhouette_score), 6), format(numeric(item.inertia), 4)])} />}
    {Object.keys(record(m.thresholds ?? m.final_thresholds)).length > 0 && <details><summary className="cursor-pointer text-sm">Ngưỡng phân loại của mô hình</summary><pre className="mt-2 whitespace-pre-wrap break-words rounded bg-muted p-3 text-xs">{JSON.stringify(m.thresholds ?? m.final_thresholds, null, 2)}</pre></details>}
  </div>;
}

function Workspace({ kind }: { kind: ModelKind }) {
  const { session } = useSession();
  const admin = session.status === "authenticated" && canManage(session.user.role);
  const [maxK, setMaxK] = useState(5), [page, setPage] = useState(1), [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [busy, setBusy] = useState(""), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const history = useGatewayQuery<PageResult<ModelRun>>(`/api/${kind}/runs${query({ page, page_size: 10 })}`, revision);
  const current = useGatewayQuery<ModelRun>(selected ? `/api/${kind}/runs/${selected}` : `/api/${kind}/latest`, revision);
  async function perform(action: "train" | "run") {
    if (!admin || busy) return;
    if (kind === "clustering" && action === "train" && (!Number.isInteger(maxK) || maxK < 2 || maxK > 8)) { setError("K tối đa phải là số nguyên từ 2 đến 8."); return; }
    setBusy(action); setError(""); setNotice("");
    try {
      const run = await gatewayRequest<ModelRun>(modelActionPath(kind, action, maxK), { method: "POST", timeoutMs: 180000 });
      setSelected(run.id); setPage(1); setNotice(`Đã hoàn tất ${action === "train" ? "huấn luyện" : "chạy mô hình"}, lượt #${run.id}.`);
    } catch (error) { setError(error instanceof Error ? error.message : "Thao tác thất bại."); }
    finally { setBusy(""); setRevision(value => value + 1); }
  }
  return <div className="space-y-6 min-w-0">
    <PageHeading title={titles[kind]} icon={kind === "clustering" ? Shapes : kind === "prediction" ? Sparkles : ChartNoAxesCombined} eyebrow="Mô hình & Dự báo" description={kind === "clustering" ? "Khám phá các nhóm tiêu thụ điện với K-Means và đánh giá Silhouette." : kind === "prediction" ? "Theo dõi dự báo tiêu thụ điện và chất lượng mô hình Random Forest." : "Phân loại mức tiêu thụ điện, xác suất và kết quả đánh giá mô hình."} />
    <Link href="/models" className="text-sm text-primary underline underline-offset-4">Mở Model Management — lịch sử tất cả mô hình</Link>
    <p className="text-sm text-muted-foreground">Bước 1: Huấn luyện mô hình từ dữ liệu hiện có. Bước 2: Chạy để xem kết quả. Huấn luyện lại sau khi cập nhật dữ liệu.</p>
    {admin ? <Panel title="Thao tác mô hình">
      <div className="flex flex-wrap items-end gap-3">{kind === "clustering" && <label className="space-y-1 text-sm"><span className="block">K tối đa (2–8, chọn theo Silhouette)</span><Input type="number" min={2} max={8} step={1} value={maxK} onChange={event => setMaxK(Number(event.target.value))} disabled={!!busy} className="w-32" /></label>}
        <Button disabled={!!busy} onClick={() => perform("train")}>{busy === "train" ? "Đang huấn luyện…" : "Huấn luyện"}</Button>
        <Button variant="outline" disabled={!!busy} onClick={() => perform("run")}>{busy === "run" ? "Đang chạy…" : "Chạy mô hình"}</Button>
      </div>
      {busy && <p role="status" className="text-sm">Yêu cầu đang được xử lý. Không gửi thêm lần nữa; nếu quá thời gian chờ, hãy kiểm tra lịch sử trước khi chạy lại.</p>}
    </Panel> : <p className="rounded-lg border border-border p-4 text-sm">Analyst có thể xem kết quả và lịch sử; chỉ Admin được huấn luyện hoặc chạy mô hình.</p>}
    {error && <p role="alert" className="rounded border border-destructive p-4 text-sm text-destructive">{error}</p>}
    {notice && <p role="status" className="text-sm text-emerald-700">{notice}</p>}
    <Panel title={selected ? `Chi tiết lượt #${selected}` : "Kết quả chạy gần nhất"} actions={<Button variant="outline" disabled={!!busy} onClick={() => { setSelected(null); setRevision(value => value + 1); }}>Tải kết quả mới nhất</Button>}>
      <QueryState resource={current} empty="Chưa có kết quả chạy thành công. Admin hãy huấn luyện rồi chạy mô hình.">{run => <ModelResult run={run} />}</QueryState>
    </Panel>
    <Panel title="Lịch sử mô hình" actions={<Button variant="outline" onClick={() => setRevision(value => value + 1)}>Tải lại</Button>}>
      <QueryState resource={history}>{data => <div className="space-y-4">{!data.items.length ? <p role="status">Chưa có lịch sử.</p> : <DataTable caption="Lịch sử chạy mô hình" headers={["ID", "Giai đoạn", "Trạng thái", "Thời gian", "Chi tiết"]} rows={data.items.map(run => [run.id, String(run.parameters?.stage ?? "—"), <StatusBadge key="status" status={run.status} />, new Date(run.created_at).toLocaleString("vi-VN"), <Button key={run.id} size="sm" variant="outline" disabled={!!busy} onClick={() => setSelected(run.id)}>Xem</Button>])} />}<Pagination page={page} pages={data.pages} total={data.total} onChange={setPage} /></div>}</QueryState>
    </Panel>
  </div>;
}
export function ModelWorkspace({ kind }: { kind: ModelKind }) { return <AppLayout><Workspace key={kind} kind={kind} /></AppLayout>; }
