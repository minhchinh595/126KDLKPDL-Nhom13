"use client";
import { useState, type FormEvent } from "react";
import { Settings2 } from "lucide-react";
import { PageHeading } from "@/components/shared/page-heading";
import { AppLayout } from "@/components/layout/app-layout";
import { useSession } from "@/components/auth/session-provider";
import { canManage, gatewayBase, gatewayRequest, query, type User, type PageResult, type Role } from "@/lib/gateway";
import { Panel, DataTable, Selector } from "@/components/analysis/analysis-shared";
import { QueryState, useGatewayQuery, Pagination } from "@/components/shared/gateway-resource";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function UsersPanel() {
  const { session, refresh: refreshSession } = useSession();
  const [page, setPage] = useState(1), [revision, setRevision] = useState(0);
  const [search, setSearch] = useState(""), [applied, setApplied] = useState("");
  const [username, setUsername] = useState(""), [email, setEmail] = useState(""), [password, setPassword] = useState(""), [confirm, setConfirm] = useState("");
  const [role, setRole] = useState<Role>("analyst");
  const [editing, setEditing] = useState<User | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const users = useGatewayQuery<PageResult<User>>(`/api/users${query({ page, page_size: 10, search: applied })}`, revision);
  const admin = session.status === "authenticated" && canManage(session.user.role);
  async function create(event: FormEvent) {
    event.preventDefault(); if (!admin || busy) return;
    setError(""); setNotice("");
    if (username.trim().length < 2) { setError("Tên người dùng phải có ít nhất 2 ký tự có nghĩa."); return; }
    if (password !== confirm) { setError("Hai lần nhập mật khẩu không giống nhau."); return; }
    setBusy(true);
    try {
      const user = await gatewayRequest<User>("/api/users", { method: "POST", body: { username: username.trim(), email: email.trim(), password, role } });
      setNotice(`Đã tạo ${user.role === "analyst" ? "Analyst" : "Admin"}: ${user.email}. Có thể đăng xuất và dùng tài khoản này để kiểm tra phân quyền.`);
      setPassword(""); setConfirm(""); setUsername(""); setEmail(""); setPage(1); setSearch(""); setApplied(""); setRevision(value => value + 1);
    } catch (error) { setError(error instanceof Error ? error.message : "Không tạo được tài khoản."); }
    finally { setBusy(false); }
  }
  async function update(path: string, body: unknown) {
    if (!admin || busy) return;
    setBusy(true); setError(""); setNotice("");
    try { const updated = await gatewayRequest<User>(path, { method: "PATCH", body }); setEditing(null); setNotice("Đã cập nhật tài khoản."); setRevision(value => value + 1); if (session.status === "authenticated" && updated.id === session.user.id && updated.role !== session.user.role) refreshSession(); }
    catch (error) { setError(error instanceof Error ? error.message : "Không cập nhật được tài khoản."); }
    finally { setBusy(false); }
  }
  return <Panel title="Quản lý tài khoản Admin / Analyst" description="Chỉ Admin được tạo tài khoản, đổi vai trò và trạng thái. Mật khẩu không được lưu trong trình duyệt.">
    <form onSubmit={create} className="space-y-4" aria-busy={busy}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4"><label className="space-y-1 text-sm"><span className="block">Tên người dùng</span><Input required minLength={2} maxLength={80} value={username} onChange={e => setUsername(e.target.value)} disabled={busy} /></label><label className="space-y-1 text-sm"><span className="block">Email</span><Input type="email" required maxLength={255} value={email} onChange={e => setEmail(e.target.value)} disabled={busy} /></label><label className="space-y-1 text-sm"><span className="block">Mật khẩu (12–128 ký tự)</span><Input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} disabled={busy} /></label><label className="space-y-1 text-sm"><span className="block">Nhập lại mật khẩu</span><Input type="password" autoComplete="new-password" required value={confirm} onChange={e => setConfirm(e.target.value)} disabled={busy} /></label></div>
      <Selector label="Vai trò tài khoản mới" value={role} onChange={value => setRole(value as Role)} options={[{ value: "analyst", label: "Analyst" }, { value: "admin", label: "Admin" }]} />
      <Button type="submit" disabled={busy}>{busy ? "Đang xử lý…" : "Tạo tài khoản"}</Button>
    </form>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}{notice && <p role="status" className="text-sm text-emerald-700">{notice}</p>}
    <form onSubmit={e => { e.preventDefault(); setApplied(search.trim()); setPage(1); }} className="flex flex-wrap gap-2"><Input aria-label="Tìm tài khoản" value={search} onChange={e => setSearch(e.target.value)} placeholder="Tên hoặc email" className="w-64 max-w-full" /><Button type="submit" variant="outline">Tìm</Button><Button type="button" variant="ghost" onClick={() => { setSearch(""); setApplied(""); setPage(1); }}>Xóa lọc</Button></form>
    <QueryState resource={users}>{data => <div className="space-y-4">{data.items.length ? <DataTable caption="Tài khoản" headers={["ID", "Tên", "Email", "Vai trò", "Trạng thái", "Thao tác"]} rows={data.items.map(user => [user.id, user.username, user.email, user.role, user.is_active ? "Hoạt động" : "Đã khóa", <div key={user.id} className="flex gap-2"><Button size="sm" variant="outline" disabled={busy} onClick={() => setEditing(user)}>Sửa</Button><Button size="sm" variant="outline" disabled={busy || (session.status === "authenticated" && user.id === session.user.id)} onClick={() => update(`/api/users/${user.id}/status`, { is_active: !user.is_active })}>{user.is_active ? "Khóa" : "Mở khóa"}</Button></div>])} /> : <p>Không có tài khoản phù hợp.</p>}<Pagination page={page} pages={data.pages} total={data.total} onChange={setPage} /></div>}</QueryState>
    {editing && <form className="rounded-lg border border-border p-4 space-y-3" onSubmit={e => { e.preventDefault(); update(`/api/users/${editing.id}`, { username: editing.username, email: editing.email, role: editing.role }); }}>
      <h3 className="font-semibold">Sửa tài khoản #{editing.id}</h3><label className="block space-y-1 text-sm"><span>Tên</span><Input required minLength={2} maxLength={80} value={editing.username} onChange={e => setEditing({ ...editing, username: e.target.value })} /></label><label className="block space-y-1 text-sm"><span>Email</span><Input type="email" required maxLength={255} value={editing.email} onChange={e => setEditing({ ...editing, email: e.target.value })} /></label><Selector label="Vai trò" value={editing.role} onChange={value => setEditing({ ...editing, role: value as Role })} options={[{ value: "analyst", label: "Analyst" }, { value: "admin", label: "Admin" }]} /><div className="flex gap-2"><Button type="submit" disabled={busy}>Lưu thay đổi</Button><Button type="button" variant="ghost" onClick={() => setEditing(null)}>Hủy</Button></div>
    </form>}
  </Panel>;
}

function Workspace() {
  const { session } = useSession();
  const health = useGatewayQuery<{ status: string; message: string; database?: string }>("/api/health/ready");
  return <div className="space-y-6 min-w-0"><PageHeading title="Cài đặt & Tài khoản" icon={Settings2} eyebrow="Hệ thống" description="Quản lý tài khoản, phân quyền và kiểm tra trạng thái kết nối hệ thống." />
    <Panel title="Phiên đăng nhập">{session.status === "authenticated" && <DataTable caption="Thông tin tài khoản" headers={["Tên", "Email", "Vai trò"]} rows={[[session.user.username, session.user.email, session.user.role]]} />}</Panel>
    <Panel title="Gateway và cơ sở dữ liệu" description="Kiểm tra trạng thái kết nối và khả năng truy cập dữ liệu của hệ thống." actions={<Button variant="outline" onClick={health.retry}>Kiểm tra lại</Button>}>
      <p className="text-sm break-all">Gateway: {gatewayBase()}</p><a className="text-sm text-primary underline" href={`${gatewayBase()}/docs`} target="_blank" rel="noopener noreferrer">Mở Swagger</a>
      <QueryState resource={health}>{data => <DataTable caption="Trạng thái Gateway" headers={["Trạng thái", "Database", "Thông báo"]} rows={[[data.status, data.database ?? "Không được API cung cấp", data.message]]} />}</QueryState>
    </Panel>
    {session.status === "authenticated" && canManage(session.user.role) ? <UsersPanel /> : <p className="text-sm text-muted-foreground">Analyst không có quyền quản lý tài khoản hoặc thay đổi cấu hình backend.</p>}
  </div>;
}
export function SettingsWorkspace() { return <AppLayout><Workspace /></AppLayout>; }
