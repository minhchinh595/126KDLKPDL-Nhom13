"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Zap, LayoutDashboard, Database, TrendingUp, Shapes, Sparkles, FileCode2, Settings2, Activity, CheckCircle2, XCircle, RefreshCw, Layers, ChartNoAxesCombined } from "lucide-react";
import { Sidebar, SidebarHeader, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupLabel, SidebarGroupContent, SidebarMenu, SidebarMenuItem, SidebarMenuButton, SidebarRail, useSidebar } from "@/components/ui/sidebar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { checkBackend, type HealthResponse } from "@/lib/api";

const groups = [
  { title: "TỔNG QUAN", items: [
    { title: "Overview Dashboard", href: "/", icon: LayoutDashboard },
    { title: "Data Management", href: "/ingestion", icon: Database },
  ] },
  { title: "PHÂN TÍCH DỮ LIỆU", items: [
    { title: "Phân tích tiêu thụ", href: "/analysis/consumption", icon: ChartNoAxesCombined },
    { title: "Xu hướng & Mùa vụ", href: "/analysis/trend", icon: TrendingUp },
    { title: "Tương quan", href: "/analysis/correlation", icon: Activity },
  ] },
  { title: "MÔ HÌNH & DỰ BÁO", items: [
    { title: "Model Management", href: "/models", icon: Layers },
    { title: "Phân cụm nhu cầu", href: "/clustering", icon: Shapes },
    { title: "Dự báo nhu cầu", href: "/prediction", icon: Sparkles },
    { title: "Phân loại tiêu thụ", href: "/classification", icon: ChartNoAxesCombined },
  ] },
];
export function AppSidebar() {
  const pathname = usePathname();
  const { isMobile, setOpenMobile } = useSidebar();
  const [status, setStatus] = React.useState<"checking" | "connected" | "disconnected">("checking");
  const [health, setHealth] = React.useState<HealthResponse | null>(null);
  const fetchHealth = React.useCallback(() => {
    checkBackend().then(data => { setStatus("connected"); setHealth(data); }).catch(() => { setStatus("disconnected"); setHealth(null); });
  }, []);
  React.useEffect(() => { fetchHealth(); const timer = setInterval(fetchHealth, 30000); return () => clearInterval(timer); }, [fetchHealth]);
  function closeMobile() { if (isMobile) setOpenMobile(false); }
  return <Sidebar collapsible="icon" className="border-r border-sidebar-border select-none">
    <SidebarHeader className="h-16 justify-center border-b border-sidebar-border px-4">
      <Link href="/" onClick={closeMobile} className="flex items-center gap-3 group-data-[collapsible=icon]:justify-center">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-amber-500 text-white shadow-sm"><Zap className="size-5 fill-current" /></div>
        <div className="min-w-0 group-data-[collapsible=icon]:hidden"><p className="text-sm font-bold tracking-tight">Electricity Analytics</p><p className="text-[10px] text-muted-foreground whitespace-nowrap">Khai phá dữ liệu · Nhóm 13</p></div>
      </Link>
    </SidebarHeader>
    <SidebarContent className="gap-0 py-1">
      {groups.map(group => <SidebarGroup key={group.title} className="px-3 py-1"><SidebarGroupLabel className="h-6 mb-0.5 text-[10px] tracking-[0.14em] text-muted-foreground">{group.title}</SidebarGroupLabel><SidebarGroupContent><SidebarMenu className="gap-0.5">
        {group.items.map(item => { const active = pathname === item.href; const Icon = item.icon; return <SidebarMenuItem key={item.href}><SidebarMenuButton render={<Link href={item.href} onClick={closeMobile} />} isActive={active} tooltip={item.title} className={`h-9 rounded-lg px-3 transition-colors ${active ? "bg-sidebar-accent text-sidebar-accent-foreground font-semibold hover:bg-sidebar-accent hover:text-sidebar-accent-foreground" : "text-muted-foreground hover:text-foreground"}`}><Icon className="size-4 shrink-0" /><span className="text-[13px]">{item.title}</span>{active && <span className="ml-auto size-1.5 rounded-full bg-amber-600 group-data-[collapsible=icon]:hidden" />}</SidebarMenuButton></SidebarMenuItem>; })}
      </SidebarMenu></SidebarGroupContent></SidebarGroup>)}
      <SidebarGroup className="px-3 py-1"><SidebarGroupLabel className="h-6 mb-0.5 text-[10px] tracking-[0.14em]">HỆ THỐNG</SidebarGroupLabel><SidebarGroupContent><SidebarMenu>
        <SidebarMenuItem><SidebarMenuButton render={<Link href="/settings" onClick={closeMobile} />} isActive={pathname === "/settings"} tooltip="Cài đặt" className="h-9 px-3 text-muted-foreground"><Settings2 className="size-4" /><span>Cài đặt & Tài khoản</span></SidebarMenuButton></SidebarMenuItem>
        <SidebarMenuItem><SidebarMenuButton render={<a href="http://localhost:8001/docs" target="_blank" rel="noopener noreferrer" />} tooltip="Tài liệu API" className="h-9 px-3 text-muted-foreground"><FileCode2 className="size-4" /><span>Tài liệu API</span><Badge variant="outline" className="ml-auto text-[9px] group-data-[collapsible=icon]:hidden">DOCS</Badge></SidebarMenuButton></SidebarMenuItem>
      </SidebarMenu></SidebarGroupContent></SidebarGroup>
    </SidebarContent>
    <SidebarFooter className="border-t border-sidebar-border p-2"><div className="flex items-center gap-2.5 rounded-xl bg-muted/60 p-3 group-data-[collapsible=icon]:p-0">
      {status === "connected" ? <CheckCircle2 className="size-4 shrink-0 text-emerald-600" /> : status === "checking" ? <Activity className="size-4 shrink-0 text-amber-600 animate-pulse" /> : <XCircle className="size-4 shrink-0 text-rose-600" />}
      <div className="min-w-0 flex-1 group-data-[collapsible=icon]:hidden"><p className="text-xs font-semibold">API Gateway</p><p className="truncate text-[10px] text-muted-foreground" title={health?.message}>{status === "connected" ? "Đã kết nối hệ thống" : status === "checking" ? "Đang kiểm tra…" : "Chưa kết nối"}</p></div>
      <Button variant="ghost" size="icon-xs" aria-label="Kiểm tra kết nối" onClick={() => { setStatus("checking"); fetchHealth(); }} className="group-data-[collapsible=icon]:hidden"><RefreshCw className={`size-3 ${status === "checking" ? "animate-spin" : ""}`} /></Button>
    </div></SidebarFooter><SidebarRail />
  </Sidebar>;
}
