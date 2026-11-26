"use client";

import { useState } from "react";
import { Layers } from "lucide-react";
import { PageHeading } from "@/components/shared/page-heading";
import { StatusBadge } from "@/components/shared/status-badge";
import Link from "next/link";
import { AppLayout } from "@/components/layout/app-layout";
import { modelRunsPath, type ModelKind, type ModelRun, type PageResult } from "@/lib/gateway";
import { Panel, DataTable, ExportCsv, Selector } from "@/components/analysis/analysis-shared";
import { Pagination, QueryState, useGatewayQuery } from "@/components/shared/gateway-resource";
import { Button } from "@/components/ui/button";
import { ModelResult } from "./model-workspace";

const names: Record<ModelKind, string> = { clustering: "Clustering", prediction: "Prediction", classification: "Classification" };
const statuses: Record<ModelRun["status"], string> = { queued: "Đang chờ", running: "Đang chạy", completed: "Hoàn tất", failed: "Thất bại" };
function Workspace() {
  const [kind, setKind] = useState<ModelKind | "">("");
  const [status, setStatus] = useState<ModelRun["status"] | "">("");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1), [pageSize, setPageSize] = useState(10), [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const history = useGatewayQuery<PageResult<ModelRun>>(modelRunsPath({ modelType: kind, status, order, page, pageSize }), revision);
  const detail = useGatewayQuery<ModelRun>(selected === null ? null : `/api/model-runs/${selected}`, revision);
  function changeFilter() { setPage(1); setSelected(null); }
  function reset() { setKind(""); setStatus(""); setOrder("desc"); setPageSize(10); changeFilter(); }
  return <div className="space-y-6 min-w-0">
    <PageHeading title="Model Management" icon={Layers} eyebrow="Mô hình & Dự báo" description="Theo dõi kết quả, chất lượng và lịch sử hoạt động của các mô hình." />
    <p className="text-sm text-muted-foreground">Quản lý kết quả và lịch sử của cả ba mô hình. Admin thực hiện huấn luyện/chạy tại từng trang mô hình; Analyst có quyền xem.</p>
    <nav aria-label="Các mô hình" className="flex flex-wrap gap-2">{(Object.keys(names) as ModelKind[]).map(model => <Link key={model} href={`/${model}`} className="rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted">{names[model]}</Link>)}</nav>
    <Panel title="Bộ lọc lịch sử">
      <div className="flex flex-wrap items-end gap-3">
        <Selector label="Loại mô hình" value={kind} onChange={value => { setKind(value as ModelKind | ""); changeFilter(); }} options={[{ value: "", label: "Tất cả mô hình" }, ...Object.entries(names).map(([value, label]) => ({ value, label }))]} />
        <Selector label="Trạng thái lượt chạy" value={status} onChange={value => { setStatus(value as ModelRun["status"] | ""); changeFilter(); }} options={[{ value: "", label: "Tất cả trạng thái" }, ...Object.entries(statuses).map(([value, label]) => ({ value, label }))]} />
        <Selector label="Thứ tự thời gian" value={order} onChange={value => { setOrder(value as "asc" | "desc"); changeFilter(); }} options={[{ value: "desc", label: "Mới nhất trước" }, { value: "asc", label: "Cũ nhất trước" }]} />
        <Selector label="Số lượt / trang" value={String(pageSize)} onChange={value => { setPageSize(Number(value)); changeFilter(); }} options={[10, 20, 50, 100].map(value => ({ value: String(value), label: String(value) }))} />
        <Button variant="ghost" onClick={reset}>Đặt lại bộ lọc</Button>
      </div>
    </Panel>
    <Panel title="Lịch sử tất cả mô hình" description="Bộ lọc và phân trang được xử lý bởi Gateway. CSV xuất các lượt đang hiển thị trên trang hiện tại." actions={<Button variant="outline" onClick={() => setRevision(value => value + 1)}>Tải lại</Button>}>
      <QueryState resource={history}>{data => <div className="space-y-4">
        {data.items.length === 0 ? <p role="status">Chưa có lượt chạy phù hợp. Hãy đổi bộ lọc hoặc mở trang mô hình để huấn luyện/chạy bằng tài khoản Admin.</p> : <>
          <DataTable caption="Lịch sử tổng hợp mô hình" headers={["ID", "Mô hình", "Giai đoạn", "Trạng thái", "Thời gian", "Lỗi", "Chi tiết"]} rows={data.items.map(run => [run.id, names[run.model_type], String(run.parameters?.stage ?? "—"), <StatusBadge key="status" status={run.status} />, new Date(run.created_at).toLocaleString("vi-VN"), run.error_message ?? "—", <Button key={run.id} variant="outline" size="sm" onClick={() => setSelected(run.id)}>Xem lượt #{run.id}</Button>])} />
          <ExportCsv filename={`model-history-page-${page}.csv`} headers={["ID", "Model", "Stage", "Status", "Created at", "Error"]} rows={data.items.map(run => [run.id, run.model_type, String(run.parameters?.stage ?? ""), run.status, run.created_at, run.error_message])} />
        </>}
        <Pagination page={page} pages={data.pages} total={data.total} onChange={value => { setPage(value); setSelected(null); }} />
      </div>}</QueryState>
    </Panel>
    {selected !== null && <Panel title={`Chi tiết lượt #${selected}`} actions={<Button variant="ghost" onClick={() => setSelected(null)}>Đóng chi tiết</Button>}><QueryState resource={detail} empty="Lượt chạy không còn tồn tại hoặc không thuộc quyền truy cập hiện tại.">{run => <ModelResult run={run} requireH2={run.model_type === "prediction" || run.model_type === "classification"} />}</QueryState></Panel>}
  </div>;
}
export function ModelManagement() { return <AppLayout><Workspace /></AppLayout>; }
