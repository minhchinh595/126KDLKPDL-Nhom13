"use client";

import { useState, type FormEvent } from "react";
import { Zap, ShieldCheck } from "lucide-react";
import { loginForDemand } from "@/lib/demand-api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export function DemandLogin({ onSuccess }: { onSuccess: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError("");
    try {
      await loginForDemand(email, password);
      setPassword(""); onSuccess();
    } catch (failure) {
      setPassword("");
      setError(failure instanceof Error ? failure.message : "Không thể đăng nhập.");
    } finally { setBusy(false); }
  }
  return <Card className="mx-auto w-full max-w-md p-6 sm:p-8 gap-6 shadow-xl">
    <div className="flex items-center gap-3"><div className="flex size-11 items-center justify-center rounded-xl bg-amber-500 text-white"><Zap className="size-6 fill-current" /></div><div><p className="font-semibold">Electricity Analytics</p><p className="text-xs text-muted-foreground">Khai phá dữ liệu · Nhóm 13</p></div></div>
    <div className="space-y-2"><h1 className="text-xl font-semibold">Đăng nhập để xem biểu đồ</h1><p className="text-sm text-muted-foreground">Đăng nhập bằng tài khoản Admin hoặc Analyst để truy cập dữ liệu và các mô hình phân tích.</p></div>
    <form onSubmit={submit} className="space-y-4" aria-busy={busy}>
      <label className="block space-y-1 text-sm"><span>Email</span><Input type="email" autoComplete="username" required maxLength={255} value={email} onChange={e => setEmail(e.target.value)} disabled={busy} /></label>
      <label className="block space-y-1 text-sm"><span>Mật khẩu</span><Input type="password" autoComplete="current-password" required maxLength={256} value={password} onChange={e => setPassword(e.target.value)} disabled={busy} /></label>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <Button type="submit" disabled={busy} className="w-full">{busy ? "Đang đăng nhập…" : "Đăng nhập và tải biểu đồ"}</Button>
    </form>
    <p className="flex items-start gap-2 text-xs text-muted-foreground"><ShieldCheck className="size-4 shrink-0 text-emerald-600" />Phiên đăng nhập được bảo vệ. Quyền truy cập theo vai trò tài khoản.</p>
  </Card>;
}
