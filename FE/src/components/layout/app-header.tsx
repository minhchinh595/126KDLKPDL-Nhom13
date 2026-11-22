"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { SidebarTrigger } from "@/components/ui/sidebar";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Badge } from "@/components/ui/badge";
import { Database, ExternalLink, Zap } from "lucide-react";
import { checkBackend } from "@/lib/api";

const ROUTE_LABELS: Record<string, string> = {
  "/": "Tổng quan Dashboard",
  "/ingestion": "Dữ liệu & Thu thập",
  "/analysis": "Quy luật Tiêu thụ",
  "/clustering": "Phân cụm Nhu cầu",
  "/prediction": "Dự đoán Nhu cầu",
  "/settings": "Cấu hình Hệ thống",
};

export function AppHeader() {
  const pathname = usePathname();
  const currentLabel = ROUTE_LABELS[pathname] || "Chi tiết";
  const [isBackendUp, setIsBackendUp] = React.useState<boolean | null>(null);

  React.useEffect(() => {
    let active = true;
    checkBackend()
      .then(() => {
        if (active) setIsBackendUp(true);
      })
      .catch(() => {
        if (active) setIsBackendUp(false);
      });
    return () => {
      active = false;
    };
  }, [pathname]);

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between gap-4 border-b border-border bg-background/95 px-4 backdrop-blur-md">
      {/* Left: Sidebar trigger & Breadcrumb */}
      <div className="flex items-center gap-3 min-w-0">
        <SidebarTrigger className="-ml-1" />
        <div className="h-4 w-px bg-border" />
        <Breadcrumb className="hidden sm:block">
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink render={<Link href="/" />}>
                Trang chủ
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage className="font-semibold text-foreground">
                {currentLabel}
              </BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      </div>

      {/* Right: Quick Scope Badges, Backend Status & Actions */}
      <div className="flex items-center gap-2.5">
        {/* Scope Pills */}
        <div className="hidden lg:flex items-center gap-1.5">
          <Badge variant="outline" className="gap-1 px-2 py-0.5 text-[11px] font-normal border-amber-500/30 bg-amber-500/5 text-amber-700 dark:text-amber-300">
            <Zap className="size-3 text-amber-500" />
            <span>Việt Nam (VNM)</span>
          </Badge>
          <Badge variant="outline" className="gap-1 px-2 py-0.5 text-[11px] font-normal border-blue-500/30 bg-blue-500/5 text-blue-700 dark:text-blue-300">
            <Database className="size-3 text-blue-500" />
            <span>Ember Monthly Demand</span>
          </Badge>
        </div>

        {/* Backend live status indicator */}
        <div className="flex items-center gap-1.5 px-2 py-1 rounded-full border border-border text-xs bg-muted/40">
          <span
            className={`size-2 rounded-full ${
              isBackendUp === true
                ? "bg-emerald-500 shadow-xs shadow-emerald-500"
                : isBackendUp === false
                ? "bg-rose-500"
                : "bg-amber-400 animate-pulse"
            }`}
          />
          <span className="text-[11px] font-medium text-muted-foreground hidden sm:inline">
            {isBackendUp === true
              ? "API Online"
              : isBackendUp === false
              ? "API Offline"
              : "Checking..."}
          </span>
        </div>

        {/* Quick Docs Link */}
        <a
          href="http://localhost:8000/docs"
          target="_blank"
          rel="noopener noreferrer"
          title="Mở FastAPI Swagger Docs"
          className="h-8 gap-1.5 text-xs hidden md:inline-flex items-center justify-center rounded-lg border border-border bg-background px-2.5 font-medium hover:bg-muted hover:text-foreground transition-colors"
        >
          <span>FastAPI Docs</span>
          <ExternalLink className="size-3 text-muted-foreground" />
        </a>
      </div>
    </header>
  );
}
