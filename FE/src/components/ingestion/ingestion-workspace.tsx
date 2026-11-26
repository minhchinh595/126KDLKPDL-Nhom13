"use client";

import { useState } from "react";
import { Database } from "lucide-react";
import { PageHeading } from "@/components/shared/page-heading";
import { StatusBadge } from "@/components/shared/status-badge";
import { AppLayout } from "@/components/layout/app-layout";
import { type Dataset, type PageResult, type ImportHistory } from "@/lib/gateway";
import { Panel, DataTable } from "@/components/analysis/analysis-shared";
import { QueryState, useGatewayQuery, Pagination } from "@/components/shared/gateway-resource";
import { Button } from "@/components/ui/button";
import { query } from "@/lib/gateway";

function Workspace() {
  const [search, setSearch] = useState(""), [appliedSearch, setAppliedSearch] = useState(""), [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0), [selected, setSelected] = useState<number | null>(null);
  const datasets = useGatewayQuery<PageResult<Dataset>>(`/api/datasets${query({ page, page_size: 10, search: appliedSearch })}`, revision);
  const history = useGatewayQuery<ImportHistory[]>(selected ? `/api/datasets/${selected}/history` : null, revision);
  const sync = useGatewayQuery<{ configured: boolean; latest_import: ImportHistory | null }>("/api/datasets/sync/status", revision);
  const detail = useGatewayQuery<Dataset>(selected ? `/api/datasets/${selected}` : null, revision);
  return <div className="space-y-6 min-w-0"><PageHeading title="Data Management" icon={Database} eyebrow="Open Electricity NEM" description="Theo dõi metadata dataset và lịch sử. NEM ingestion được thực hiện bởi worker chuyên biệt; trang này không upload CSV hoặc khởi chạy import." />
    <div role="note" className="rounded-lg border border-border bg-muted/30 p-4 text-sm"><strong>Nguồn hoạt động:</strong> Open Electricity NEM · network-level · daily demand MW và các metric đã xác minh. CSV upload/import/sync legacy không được hỗ trợ trong Gateway hiện tại; trang không gửi các request ghi.</div>
    <Panel title="Danh sách dataset" actions={<Button variant="outline" onClick={() => setRevision(value => value + 1)}>Tải lại</Button>}>
      <form onSubmit={event => { event.preventDefault(); setAppliedSearch(search.trim()); setPage(1); }} className="flex flex-wrap gap-2"><input aria-label="Tìm dataset" placeholder="Tên hoặc nguồn" value={search} onChange={event => setSearch(event.target.value)} className="h-9 w-64 max-w-full rounded-md border border-input bg-background px-3 text-sm" /><Button type="submit" variant="outline">Tìm</Button><Button variant="ghost" type="button" onClick={() => { setSearch(""); setAppliedSearch(""); setPage(1); }}>Xóa lọc</Button></form>
      <QueryState resource={datasets}>{data => <div className="space-y-4">{data.items.length ? <DataTable caption="Dataset" headers={["ID", "Vai trò", "Tên", "Nguồn", "Số observations", "Trạng thái", "Khoảng ngày", "Metadata"]} rows={data.items.map(dataset => [dataset.id, dataset.source_role === "active_nem" ? "Active NEM" : "Legacy", dataset.name, dataset.source, dataset.record_count, <StatusBadge key="status" status={dataset.status} />, `${dataset.start_date ?? "—"} / ${dataset.end_date ?? "—"}`, <Button key={dataset.id} size="sm" variant="outline" onClick={() => setSelected(dataset.id)}>Chi tiết & lịch sử</Button>])} /> : <p role="status">Chưa có dataset phù hợp.</p>}<Pagination page={page} pages={data.pages} total={data.total} onChange={setPage} /></div>}</QueryState>
    </Panel>
    {selected !== null && <Panel title={`Chi tiết dataset #${selected}`} actions={<Button variant="ghost" onClick={() => setSelected(null)}>Đóng</Button>}><QueryState resource={detail} empty="Dataset không còn tồn tại.">{dataset => <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm break-words">{[["Vai trò", dataset.source_role === "active_nem" ? "Active Open Electricity NEM" : "Legacy metadata"], ["Tên dataset", dataset.name], ["Nguồn", dataset.source], ["File/source descriptor", dataset.file_name], ["Mô tả", dataset.description ?? "—"], ["Số observations", String(dataset.record_count)], ["Trạng thái", dataset.status], ["Khoảng ngày", `${dataset.start_date ?? "—"} / ${dataset.end_date ?? "—"}`], ["Tạo lúc", new Date(dataset.created_at).toLocaleString("vi-VN")], ["Cập nhật lúc", new Date(dataset.updated_at).toLocaleString("vi-VN")]].map(([label, value]) => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd className="mt-1 font-medium">{value}</dd></div>)}</dl>}</QueryState></Panel>}
    {selected !== null && <Panel title={`Lịch sử import metadata #${selected}`}><QueryState resource={history}>{rows => rows.length ? <DataTable caption="Lịch sử import" headers={["ID", "Mode", "Trạng thái", "Rows", "Thêm", "Cập nhật", "Bỏ qua", "Lỗi", "Chi tiết"]} rows={rows.map(item => [item.id, item.mode, <StatusBadge key="status" status={item.status} />, item.rows_read, item.inserted_count, item.updated_count, item.skipped_count, item.error_count, item.error_message ?? "—"])} /> : <p role="status">Dataset này chưa có lịch sử import.</p>}</QueryState></Panel>}
    <Panel title="Trạng thái đồng bộ legacy"><QueryState resource={sync}>{status => <div className="space-y-2"><p className="text-sm">{status.configured ? "Backend báo có cấu hình sync; luồng này không đại diện cho NEM worker." : "Gateway không cấu hình CSV/URL sync. NEM worker là tiến trình riêng và không được khởi chạy từ Frontend."}</p>{status.latest_import && <p className="text-xs text-muted-foreground">Lần gần nhất: {status.latest_import.status} · {status.latest_import.completed_at ?? status.latest_import.started_at} · {status.latest_import.error_message ?? ""}</p>}</div>}</QueryState></Panel>
  </div>;
}
export function IngestionWorkspace() { return <AppLayout><Workspace /></AppLayout>; }
