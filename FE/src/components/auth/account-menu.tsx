"use client";
import { useState } from "react";
import { useSession } from "./session-provider";
import { Button } from "@/components/ui/button";

export function AccountMenu() {
  const { session, logout } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (session.status !== "authenticated") return null;
  return <div className="flex flex-wrap items-center gap-2 text-xs">
    <span className="max-w-36 truncate" title={session.user.email}>{session.user.username} · {session.user.role === "admin" ? "Admin" : "Analyst"}</span>
    <Button size="sm" variant="outline" disabled={busy} onClick={async () => { setBusy(true); setError(""); try { await logout(); } catch (error) { setError(error instanceof Error ? error.message : "Không đăng xuất được"); } finally { setBusy(false); } }}>Đăng xuất</Button>
    {error && <span role="alert" className="text-destructive">{error}</span>}
  </div>;
}
