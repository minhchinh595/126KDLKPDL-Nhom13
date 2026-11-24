"use client";

import { useState, type FormEvent } from "react";
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
  return <Card className="mx-auto w-full max-w-md p-6 gap-4">
    <div className="space-y-2"><h1 className="text-xl font-semibold">Đăng nhập để xem biểu đồ</h1><p className="text-sm text-muted-foreground">Dùng email và mật khẩu tài khoản Admin hoặc Analyst đã tạo trên backend. Phiên đăng nhập có thể đã hết hạn.</p></div>
    <form onSubmit={submit} className="space-y-4" aria-busy={busy}>
      <label className="block space-y-1 text-sm"><span>Email</span><Input type="email" autoComplete="username" required maxLength={255} value={email} onChange={e => setEmail(e.target.value)} disabled={busy} /></label>
      <label className="block space-y-1 text-sm"><span>Mật khẩu</span><Input type="password" autoComplete="current-password" required maxLength={256} value={password} onChange={e => setPassword(e.target.value)} disabled={busy} /></label>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <Button type="submit" disabled={busy} className="w-full">{busy ? "Đang đăng nhập…" : "Đăng nhập và tải biểu đồ"}</Button>
    </form>
    <p className="text-xs text-muted-foreground">Không cần đăng nhập qua Swagger. Trình duyệt giữ phiên bằng cookie HttpOnly.</p>
  </Card>;
}
