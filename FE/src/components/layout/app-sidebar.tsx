"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Zap,
  LayoutDashboard,
  Database,
  TrendingUp,
  Shapes,
  Sparkles,
  FileCode2,
  Settings2,
  Activity,
  CheckCircle2,
  XCircle,
  RefreshCw,
} from "lucide-react";

import {
  Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarRail,
} from "@/components/ui/sidebar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { checkBackend, type HealthResponse } from "@/lib/api";

const MAIN_NAV_ITEMS = [
  {
    title: "Tổng quan Dashboard",
    href: "/",
    icon: LayoutDashboard,
    badge: "93 kỳ",
    description: "Chỉ số tiêu thụ & xu hướng toàn cảnh",
  },
  {
    title: "Dữ liệu & Thu thập",
    href: "/ingestion",
    icon: Database,
    badge: "Ember VNM",
    description: "Quản lý nguồn & lịch sử nạp dữ liệu",
  },
  {
    title: "Quy luật Tiêu thụ",
    href: "/analysis",
    icon: TrendingUp,
    badge: "Mùa vụ",
    description: "Nhận diện quy luật tháng & tăng trưởng",
  },
  {
    title: "Phân cụm Nhu cầu",
    href: "/clustering",
    icon: Shapes,
    badge: "3 Cụm",
    description: "Phân nhóm đặc điểm tiêu thụ điện",
  },
  {
    title: "Dự đoán Nhu cầu",
    href: "/prediction",
    icon: Sparkles,
    badge: "AI/ML",
    description: "Dự báo nhu cầu điện năng tương lai",
  },
];

const SYSTEM_NAV_ITEMS = [
  {
    title: "Tài liệu API (FastAPI)",
    href: "http://localhost:8000/docs",
    icon: FileCode2,
    external: true,
  },
  {
    title: "Cấu hình Hệ thống",
    href: "/settings",
    icon: Settings2,
    external: false,
  },
];

export function AppSidebar() {
  const pathname = usePathname();
  const [backendStatus, setBackendStatus] = React.useState<"connected" | "disconnected" | "checking">("checking");
  const [healthData, setHealthData] = React.useState<HealthResponse | null>(null);

  const fetchHealth = React.useCallback(() => {
    checkBackend()
      .then((res) => {
        setBackendStatus("connected");
        setHealthData(res);
      })
      .catch(() => {
        setBackendStatus("disconnected");
        setHealthData(null);
      });
  }, []);

  React.useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 15000);
    return () => clearInterval(interval);
  }, [fetchHealth]);

  const handleManualRefresh = () => {
    setBackendStatus("checking");
    fetchHealth();
  };

  return (
    <Sidebar collapsible="icon" className="border-r border-border bg-sidebar select-none">
      {/* Brand Header */}
      <SidebarHeader className="border-b border-sidebar-border px-3 py-3">
        <Link href="/" className="flex items-center gap-2.5 px-1 group-data-[collapsible=icon]:justify-center">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-amber-500 text-white shadow-sm shadow-amber-500/25">
            <Zap className="size-5 fill-current" />
          </div>
          <div className="flex flex-col overflow-hidden text-left leading-tight group-data-[collapsible=icon]:hidden">
            <span className="truncate font-bold tracking-tight text-foreground text-sm">
              Electricity Analytics
            </span>
            <span className="truncate text-[11px] text-muted-foreground">
              Kho Dữ Liệu • Nhóm 13
            </span>
          </div>
        </Link>
      </SidebarHeader>

      {/* Main Navigation */}
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
            Phân tích & Khai phá
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {MAIN_NAV_ITEMS.map((item) => {
                const isActive = pathname === item.href;
                const Icon = item.icon;
                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      render={<Link href={item.href} />}
                      isActive={isActive}
                      tooltip={item.title}
                      className={isActive ? "bg-primary text-primary-foreground font-medium hover:bg-primary/90 hover:text-primary-foreground" : ""}
                    >
                      <div className="flex items-center justify-between gap-2 w-full">
                        <div className="flex items-center gap-2.5 min-w-0">
                          <Icon className="size-4 shrink-0" />
                          <span className="truncate text-sm">{item.title}</span>
                        </div>
                        {item.badge && (
                          <Badge
                            variant={isActive ? "secondary" : "outline"}
                            className="text-[10px] px-1.5 py-0 h-4 font-normal group-data-[collapsible=icon]:hidden"
                          >
                            {item.badge}
                          </Badge>
                        )}
                      </div>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
            Hệ thống & Tích hợp
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {SYSTEM_NAV_ITEMS.map((item) => {
                const isActive = pathname === item.href;
                const Icon = item.icon;
                return (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton
                      render={
                        item.external ? (
                          <a href={item.href} target="_blank" rel="noopener noreferrer" />
                        ) : (
                          <Link href={item.href} />
                        )
                      }
                      isActive={isActive}
                      tooltip={item.title}
                    >
                      <div className="flex items-center justify-between gap-2 w-full">
                        <div className="flex items-center gap-2.5 min-w-0">
                          <Icon className="size-4 shrink-0" />
                          <span className="truncate text-sm">{item.title}</span>
                        </div>
                        {item.external && (
                          <Badge variant="outline" className="text-[9px] px-1 h-3.5 group-data-[collapsible=icon]:hidden">
                            DOCS
                          </Badge>
                        )}
                      </div>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      {/* Footer Backend Status */}
      <SidebarFooter className="border-t border-sidebar-border p-3">
        <div className="flex flex-col gap-2 rounded-lg border border-border bg-card/60 p-2.5 group-data-[collapsible=icon]:p-1.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              {backendStatus === "connected" ? (
                <CheckCircle2 className="size-4 text-emerald-500 shrink-0" />
              ) : backendStatus === "checking" ? (
                <Activity className="size-4 text-amber-500 animate-pulse shrink-0" />
              ) : (
                <XCircle className="size-4 text-rose-500 shrink-0" />
              )}
              <div className="flex flex-col min-w-0 group-data-[collapsible=icon]:hidden">
                <span className="text-xs font-medium text-foreground truncate">
                  FastAPI Backend
                </span>
                <span className="text-[11px] text-muted-foreground truncate">
                  {backendStatus === "connected"
                    ? (healthData?.message || "Đang hoạt động")
                    : backendStatus === "checking"
                    ? "Đang kết nối..."
                    : "Chưa kết nối (cổng 8000)"}
                </span>
              </div>
            </div>
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={handleManualRefresh}
              title="Kiểm tra lại kết nối"
              className="text-muted-foreground hover:text-foreground group-data-[collapsible=icon]:hidden"
            >
              <RefreshCw className={`size-3 ${backendStatus === "checking" ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </div>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}
