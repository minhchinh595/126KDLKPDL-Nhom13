"use client";

import * as React from "react";
import { AppLayout } from "@/components/layout/app-layout";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Settings2, Server, Database, RefreshCw } from "lucide-react";
import { checkBackend, type HealthResponse } from "@/lib/api";

export default function SettingsPage() {
  const [status, setStatus] = React.useState<"connected" | "disconnected" | "checking">("checking");
  const [healthData, setHealthData] = React.useState<HealthResponse | null>(null);

  const testConnection = React.useCallback(() => {
    checkBackend()
      .then((res) => {
        setStatus("connected");
        setHealthData(res);
      })
      .catch(() => {
        setStatus("disconnected");
        setHealthData(null);
      });
  }, []);

  React.useEffect(() => {
    testConnection();
  }, [testConnection]);

  const handleManualTest = () => {
    setStatus("checking");
    testConnection();
  };

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex flex-col gap-2 border-b border-border/80 pb-5">
          <div className="flex items-center gap-2.5">
            <div className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Settings2 className="size-5" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              Cấu hình & Trạng thái Hệ thống
            </h1>
            <Badge variant="outline" className="text-xs">
              System Settings
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Quản lý kết nối Backend FastAPI, cấu hình dữ liệu và tham số môi trường hệ thống.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Backend Connection Card */}
          <Card className="border border-border shadow-xs">
            <CardHeader className="border-b border-border/60 pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Server className="size-4 text-blue-500" />
                  <CardTitle className="text-sm font-semibold">FastAPI Backend API</CardTitle>
                </div>
                <Badge
                  variant={status === "connected" ? "default" : status === "checking" ? "secondary" : "destructive"}
                  className="text-xs"
                >
                  {status === "connected" ? "Online" : status === "checking" ? "Checking" : "Offline"}
                </Badge>
              </div>
              <CardDescription className="text-xs">
                Endpoint API cung cấp dịch vụ phân tích và dự báo: http://localhost:8000
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-4 space-y-3">
              <div className="rounded-lg bg-muted/40 p-3 text-xs space-y-1.5 font-mono">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">URL:</span>
                  <span className="font-semibold text-foreground">http://localhost:8000</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Health Check:</span>
                  <span className="font-semibold text-foreground">/api/health</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Phản hồi:</span>
                  <span className="text-foreground">
                    {healthData ? JSON.stringify(healthData) : status === "checking" ? "Đang gửi ping..." : "Không thể kết nối"}
                  </span>
                </div>
              </div>

              <div className="flex justify-end">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleManualTest}
                  disabled={status === "checking"}
                  className="text-xs gap-1.5 h-8"
                >
                  <RefreshCw className={`size-3.5 ${status === "checking" ? "animate-spin" : ""}`} />
                  <span>Kiểm tra lại</span>
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Database & Storage Card */}
          <Card className="border border-border shadow-xs">
            <CardHeader className="border-b border-border/60 pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Database className="size-4 text-emerald-500" />
                  <CardTitle className="text-sm font-semibold">Cơ sở Dữ liệu & Tập tin</CardTitle>
                </div>
                <Badge variant="outline" className="text-xs text-emerald-600 border-emerald-500/30">
                  Ready
                </Badge>
              </div>
              <CardDescription className="text-xs">
                Dữ liệu Ember Monthly Electricity Demand Việt Nam (2019 - 2026)
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-4 space-y-3">
              <div className="rounded-lg bg-muted/40 p-3 text-xs space-y-1.5 font-mono">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">File gốc:</span>
                  <span className="font-semibold text-foreground">ember-monthly-generation.csv</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">File đã xử lý:</span>
                  <span className="font-semibold text-foreground">vietnam_electricity_demand.csv</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Tổng số dòng:</span>
                  <span className="font-semibold text-emerald-600">93 tháng</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </AppLayout>
  );
}
