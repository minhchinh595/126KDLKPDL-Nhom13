"use client";

import * as React from "react";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { AppHeader } from "@/components/layout/app-header";
import { DemandDataProvider } from "@/components/dashboard/demand-data-provider";

import { AuthGate } from "@/components/auth/session-provider";

interface AppLayoutProps {
  children: React.ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  return (
    <AuthGate><DemandDataProvider><SidebarProvider defaultOpen={true}>
      <AppSidebar />
      <SidebarInset className="flex flex-col min-w-0 bg-background">
        <AppHeader />
        <main id="main-content" className="flex-1 min-w-0 p-4 sm:p-6 lg:p-8">
          <div className="mx-auto w-full max-w-[1440px] space-y-6">
            {children}
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider></DemandDataProvider></AuthGate>
  );
}
