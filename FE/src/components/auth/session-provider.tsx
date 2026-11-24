"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { gatewayRequest, parseUser, type User } from "@/lib/gateway";
import { DemandApiError } from "@/lib/demand-api";
import { DemandLogin } from "@/components/dashboard/demand-login";
import { Button } from "@/components/ui/button";

type Session = { status: "loading" | "anonymous" } | { status: "error"; message: string } | { status: "authenticated"; user: User };
const Context = createContext<{ session: Session; refresh: () => void; logout: () => Promise<void> } | null>(null);
export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session>({ status: "loading" });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    gatewayRequest<unknown>("/api/auth/me", { signal: controller.signal }).then(data => { if (!controller.signal.aborted) setSession({ status: "authenticated", user: parseUser(data) }); }).catch(error => {
      if (!controller.signal.aborted) setSession(error instanceof DemandApiError && error.status === 401 ? { status: "anonymous" } : { status: "error", message: error instanceof Error ? error.message : "Không kiểm tra được phiên đăng nhập." });
    });
    const expired = () => { controller.abort(); setSession({ status: "anonymous" }); };
    const revalidate = () => setRevision(value => value + 1);
    window.addEventListener("gateway-session-expired", expired);
    window.addEventListener("focus", revalidate);
    return () => { controller.abort(); window.removeEventListener("gateway-session-expired", expired); window.removeEventListener("focus", revalidate); };
  }, [revision]);
  function refresh() { setSession({ status: "loading" }); setRevision(value => value + 1); }
  async function logout() { await gatewayRequest("/api/auth/logout", { method: "POST" }); setSession({ status: "anonymous" }); }
  return <Context.Provider value={{ session, refresh, logout }}>{children}</Context.Provider>;
}
export function useSession() { const context = useContext(Context); if (!context) throw new Error("SessionProvider is required"); return context; }
export function AuthGate({ children }: { children: ReactNode }) {
  const { session, refresh } = useSession();
  if (session.status === "authenticated") return children;
  return <main className="min-h-screen flex items-center justify-center p-4 bg-background">
    {session.status === "loading" ? <p role="status">Đang kiểm tra phiên đăng nhập…</p> : session.status === "anonymous" ? <DemandLogin onSuccess={refresh} /> : session.status === "error" ? <div role="alert" className="space-y-3"><p>{session.message}</p><Button onClick={refresh}>Thử lại Gateway</Button></div> : null}
  </main>;
}
export function AdminOnly({ children }: { children: ReactNode }) {
  const { session } = useSession();
  return session.status === "authenticated" && session.user.role === "admin" ? children : <p role="status" className="rounded-lg border border-border p-4 text-sm text-muted-foreground">Chức năng này chỉ dành cho Admin. Analyst được xem dữ liệu và kết quả phân tích.</p>;
}
