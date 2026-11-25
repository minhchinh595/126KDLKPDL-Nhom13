"use client";
import { useState, type FormEvent } from "react";
import { Database } from "lucide-react";
import { PageHeading } from "@/components/shared/page-heading";
import { StatusBadge } from "@/components/shared/status-badge";
import { AppLayout } from "@/components/layout/app-layout";
import { useSession } from "@/components/auth/session-provider";
import { useDemandData } from "@/components/dashboard/demand-data-provider";
import { canManage, gatewayRequest, query, type Dataset, type PageResult, type ImportHistory, type ImportResult } from "@/lib/gateway";
import { Panel, DataTable } from "@/components/analysis/analysis-shared";
import { QueryState, useGatewayQuery, Pagination } from "@/components/shared/gateway-resource";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function Workspace() {
  const { session } = useSession();
  const { reload: reloadDemand } = useDemandData();
  const admin = session.status === "authenticated" && canManage(session.user.role);
  const [name, setName] = useState(""), [source, setSource] = useState(""), [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null), [inputVersion, setInputVersion] = useState(0);
  const [search, setSearch] = useState(""), [appliedSearch, setAppliedSearch] = useState(""), [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0), [selected, setSelected] = useState<number | null>(null);
  const [busy, setBusy] = useState(""), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const datasets = useGatewayQuery<PageResult<Dataset>>(`/api/datasets${query({ page, page_size: 10, search: appliedSearch })}`, revision);
  const history = useGatewayQuery<ImportHistory[]>(selected ? `/api/datasets/${selected}/history` : null, revision);
  const sync = useGatewayQuery<{ configured: boolean; latest_import: ImportHistory | null }>("/api/datasets/sync/status", revision);
  const detail = useGatewayQuery<Dataset>(selected ? `/api/datasets/${selected}` : null, revision);
  async function upload(event: FormEvent) {
    event.preventDefault(); if (!admin || busy) return;
    setError(""); setNotice("");
    if (name.trim().length < 2 || source.trim().length < 2) { setError("Tên dataset và nguồn phải có ít nhất 2 ký tự có nghĩa."); return; }
    if (!file || !file.name.toLowerCase().endsWith(".csv")) { setError("Vui lòng chọn file CSV."); return; }
    if (!file.size || file.size > 25 * 1024 * 1024) { setError("File CSV phải có dữ liệu và không vượt quá 25 MB; Gateway có thể áp dụng giới hạn nhỏ hơn."); return; }
    const form = new FormData(); form.set("file", file); form.set("name", name.trim()); form.set("source", source.trim()); if (description.trim()) form.set("description", description.trim());
    setBusy("upload");
    try {
      const dataset = await gatewayRequest<Dataset>("/api/datasets/upload", { method: "POST", body: form, timeoutMs: 60000 });
      setSelected(dataset.id); setPage(1); setAppliedSearch(""); setSearch(""); setFile(null); setInputVersion(value => value + 1);
      setNotice(`CSV đã qua kiểm tra và được lưu thành dataset #${dataset.id}. Nhấn Import ở dòng dataset để nạp vào kho dữ liệu.`);
    } catch (error) { setError(error instanceof Error ? error.message : "Không upload được CSV."); }
    finally { setBusy(""); setRevision(value => value + 1); }
  }
  async function mutate(path: string, action: string) {
    if (!admin || busy) return;
    setBusy(action); setError(""); setNotice("");
    try {
      const result = await gatewayRequest<ImportResult>(path, { method: "POST", timeoutMs: 120000 });
      reloadDemand();
      setSelected(result.dataset.id); setNotice(`Đã xử lý ${result.history.rows_read} dòng: thêm ${result.history.inserted_count}, cập nhật ${result.history.updated_count}, bỏ qua ${result.history.skipped_count}, lỗi ${result.history.error_count}.`);
    } catch (error) { setError(error instanceof Error ? error.message : "Không hoàn thành thao tác."); }
    finally { setBusy(""); setRevision(value => value + 1); }
  }
  return <div className="space-y-6 min-w-0"><PageHeading title="Data Management" icon={Database} eyebrow="Dữ liệu & Thu thập" description="Quản lý nguồn dữ liệu, kiểm tra CSV và theo dõi lịch sử nhập liệu." />
    <p className="text-sm text-muted-foreground">Tải CSV lên để kiểm tra, chọn Import để nạp dữ liệu, sau đó xem chi tiết và lịch sử của từng dataset.</p>
    {admin ? <Panel title="Upload và kiểm tra CSV">
      <form onSubmit={upload} className="space-y-4" aria-busy={!!busy}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4"><label className="space-y-1 text-sm"><span className="block">Tên dataset</span><Input required minLength={2} maxLength={160} value={name} onChange={e => setName(e.target.value)} disabled={!!busy} /></label><label className="space-y-1 text-sm"><span className="block">Nguồn</span><Input required minLength={2} maxLength={255} value={source} onChange={e => setSource(e.target.value)} disabled={!!busy} /></label></div>
        <label className="block space-y-1 text-sm"><span>Mô tả</span><Input value={description} onChange={e => setDescription(e.target.value)} disabled={!!busy} /></label>
        <label className="block space-y-1 text-sm"><span>File CSV (tối đa 25 MB)</span><Input key={inputVersion} type="file" accept=".csv,text/csv" required disabled={!!busy} onChange={e => setFile(e.target.files?.[0] ?? null)} /></label>
        <p className="text-xs text-muted-foreground">Các cột: country_id, country, iso3, month, metric, fuel, value, unit. Dùng VNM / demand / fuel trống / TWh; tháng dạng YYYY-MM. Backend trả lỗi nếu dữ liệu không hợp lệ.</p>
        <Button type="submit" disabled={!!busy}>{busy === "upload" ? "Đang kiểm tra và upload…" : "Upload CSV"}</Button>
      </form>
    </Panel> : <p className="rounded border border-border p-4 text-sm">Analyst được xem dataset và lịch sử. Upload, import và đồng bộ chỉ dành cho Admin.</p>}
    {error && <p role="alert" className="rounded border border-destructive p-4 text-sm text-destructive">{error}</p>}{notice && <p role="status" className="rounded border border-border p-4 text-sm">{notice}</p>}
    {busy && <p role="status" className="text-sm">Đang xử lý. Nếu hết thời gian chờ, hãy tải lại lịch sử để kiểm tra trước khi thao tác lại.</p>}
    <Panel title="Danh sách dataset" actions={<Button variant="outline" onClick={() => setRevision(value => value + 1)}>Tải lại</Button>}>
      <form onSubmit={e => { e.preventDefault(); setAppliedSearch(search.trim()); setPage(1); }} className="flex flex-wrap gap-2"><Input aria-label="Tìm dataset" placeholder="Tên hoặc nguồn" value={search} onChange={e => setSearch(e.target.value)} className="w-64 max-w-full" /><Button type="submit" variant="outline">Tìm</Button><Button variant="ghost" type="button" onClick={() => { setSearch(""); setAppliedSearch(""); setPage(1); }}>Xóa lọc</Button></form>
      <QueryState resource={datasets}>{data => <div className="space-y-4">{data.items.length ? <DataTable caption="Dataset" headers={["ID", "Tên", "Nguồn", "Số dòng", "Trạng thái", "Từ / đến", "Thao tác"]} rows={data.items.map(dataset => [dataset.id, dataset.name, dataset.source, dataset.record_count, <StatusBadge key="status" status={dataset.status} />, `${dataset.start_date ?? "—"} / ${dataset.end_date ?? "—"}`, <div key={dataset.id} className="flex gap-2"><Button size="sm" variant="outline" onClick={() => setSelected(dataset.id)}>Chi tiết & lịch sử</Button>{admin && <Button size="sm" disabled={!!busy} onClick={() => mutate(`/api/datasets/${dataset.id}/import`, `import-${dataset.id}`)}>{busy === `import-${dataset.id}` ? "Đang import…" : "Import"}</Button>}</div>])} /> : <p role="status">Chưa có dataset phù hợp.</p>}<Pagination page={page} pages={data.pages} total={data.total} onChange={setPage} /></div>}</QueryState>
    </Panel>
    {selected && <Panel title={`Chi tiết dataset #${selected}`} actions={<Button variant="ghost" onClick={() => setSelected(null)}>Đóng chi tiết</Button>}>
      <QueryState resource={detail} empty="Dataset không còn tồn tại.">{dataset => <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm break-words">
        {[["Tên dataset", dataset.name], ["Nguồn", dataset.source], ["Tên file", dataset.file_name], ["Mô tả", dataset.description ?? "—"], ["Số dòng", dataset.record_count], ["Trạng thái", dataset.status], ["Khoảng dữ liệu", `${dataset.start_date ?? "—"} / ${dataset.end_date ?? "—"}`], ["Tạo lúc", new Date(dataset.created_at).toLocaleString("vi-VN")], ["Cập nhật lúc", new Date(dataset.updated_at).toLocaleString("vi-VN")]].map(([label, value]) => <div key={label} className="min-w-0"><dt className="text-muted-foreground">{label}</dt><dd className="mt-1 font-medium">{value}</dd></div>)}
      </dl>}</QueryState>
    </Panel>}
    {selected && <Panel title={`Lịch sử dataset #${selected}`}><QueryState resource={history}>{rows => rows.length ? <DataTable caption="Lịch sử import" headers={["ID", "Chế độ", "Trạng thái", "Dòng đọc", "Thêm", "Cập nhật", "Bỏ qua", "Lỗi", "Chi tiết"]} rows={rows.map(item => [item.id, item.mode, <StatusBadge key="status" status={item.status} />, item.rows_read, item.inserted_count, item.updated_count, item.skipped_count, item.error_count, item.error_message ?? "-"])} /> : <p role="status">Chưa có lượt import cho dataset này.</p>}</QueryState></Panel>}
    <Panel title="Đồng bộ nguồn đã cấu hình"><QueryState resource={sync}>{status => <div className="space-y-3"><p className="text-sm">{status.configured ? "Gateway đã có nguồn đồng bộ." : "Backend chưa cấu hình nguồn đồng bộ."}</p>{status.latest_import && <p className="text-xs text-muted-foreground">Lần gần nhất: {status.latest_import.status} · {status.latest_import.completed_at ?? status.latest_import.started_at} · {status.latest_import.error_message ?? ""}</p>}{admin && <Button disabled={!status.configured || !!busy} onClick={() => mutate("/api/datasets/sync", "sync")}>Đồng bộ dataset</Button>}</div>}</QueryState></Panel>
  </div>;
}
export function IngestionWorkspace() { return <AppLayout><Workspace /></AppLayout>; }
