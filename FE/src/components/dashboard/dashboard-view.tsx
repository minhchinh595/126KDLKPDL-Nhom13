"use client";

import * as React from "react";
import {
  Zap,
  Flame,
  Activity,
  Sparkles,
  RefreshCw,
  Eye,
  EyeOff,
  Layers,
  Download,
} from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { MetricCard } from "@/components/dashboard/metric-card";
import { DashboardSkeleton } from "@/components/dashboard/dashboard-skeleton";
import { TrendChart } from "@/components/charts/trend-chart";
import { SeasonalityChart } from "@/components/charts/seasonality-chart";
import { ClusteringPieChart } from "@/components/charts/clustering-pie-chart";
import { KPI_DATA, RECENT_RECORDS } from "@/lib/electricity-data";

export function DashboardView() {
  const [showSkeleton, setShowSkeleton] = React.useState(false);
  const [isRefreshing, setIsRefreshing] = React.useState(false);

  const handleRefresh = () => {
    setIsRefreshing(true);
    setTimeout(() => {
      setIsRefreshing(false);
    }, 600);
  };

  return (
    <div className="space-y-6">
      {/* Top Banner & Skeleton Mode Switch */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border/80 pb-5">
        <div className="space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              Tổng quan Tiêu thụ Điện năng
            </h1>
            <Badge variant="secondary" className="gap-1 font-normal text-xs bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20">
              <Zap className="size-3 text-amber-500" />
              <span>Việt Nam (VNM)</span>
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Hệ thống phân tích mức tiêu thụ điện năng nhằm nhận diện quy luật sử dụng và dự đoán nhu cầu điện.
          </p>
        </div>

        {/* Action Controls & Skeleton Demo Toggle */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <Button
            variant={showSkeleton ? "default" : "outline"}
            size="sm"
            onClick={() => setShowSkeleton(!showSkeleton)}
            className="gap-1.5 text-xs h-8 shadow-xs"
            title="Nhấn để xem giao diện Dashboard Skeleton khi đang tải dữ liệu"
          >
            {showSkeleton ? (
              <>
                <EyeOff className="size-3.5" />
                <span>Thoát chế độ Skeleton</span>
              </>
            ) : (
              <>
                <Eye className="size-3.5" />
                <span>Xem Dashboard Skeleton</span>
              </>
            )}
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="gap-1 text-xs h-8"
            title="Làm mới dữ liệu từ nguồn"
          >
            <RefreshCw className={`size-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
            <span className="hidden sm:inline">Làm mới</span>
          </Button>
        </div>
      </div>

      {/* Render Skeleton if toggled */}
      {showSkeleton ? (
        <div className="space-y-4">
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-700 dark:text-amber-400 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Layers className="size-4 text-amber-500" />
              <span>
                <strong>Chế độ Dashboard Skeleton đang hiển thị:</strong> Khung giao diện placeholder mẫu được sử dụng cho Next.js Suspense & Streaming trong quá trình nạp dữ liệu.
              </span>
            </div>
            <Button
              size="xs"
              variant="outline"
              onClick={() => setShowSkeleton(false)}
              className="text-xs h-6 px-2 border-amber-500/30 text-amber-800 dark:text-amber-200"
            >
              Xem giao diện đầy đủ
            </Button>
          </div>
          <DashboardSkeleton />
        </div>
      ) : (
        /* Full Dashboard View */
        <div className="space-y-6">
          {/* 4 KPI Metric Cards */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              title="Nhu cầu tháng gần nhất"
              value={KPI_DATA.latestDemand}
              unit={KPI_DATA.latestDemandUnit}
              trend={KPI_DATA.growthRateYoY}
              trendLabel={`Tháng ${KPI_DATA.latestMonth} (YoY)`}
              icon={Zap}
              variant="amber"
            />
            <MetricCard
              title="Đỉnh phụ tải cao nhất"
              value={KPI_DATA.peakDemand}
              unit="TWh"
              description={`Kỷ lục hè Tháng ${KPI_DATA.peakMonth}`}
              icon={Flame}
              variant="purple"
            />
            <MetricCard
              title="Nhu cầu trung bình tháng"
              value={KPI_DATA.averageMonthlyDemand}
              unit="TWh"
              description={`Khảo sát trên ${KPI_DATA.totalRecords} kỳ (2019-2026)`}
              icon={Activity}
              variant="blue"
            />
            <MetricCard
              title="Độ chính xác mô hình dự đoán"
              value="94.6%"
              description="Sai số MAPE: 3.4% • 3 Cụm K-Means"
              icon={Sparkles}
              variant="emerald"
            />
          </div>

          {/* Main Chart: Demand Trend over Time */}
          <Card className="border border-border shadow-xs">
            <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-border/60 pb-4">
              <div>
                <CardTitle className="text-base font-semibold text-foreground flex items-center gap-2">
                  <span>Xu hướng Nhu cầu Điện năng Việt Nam (2019 - 2026)</span>
                  <Badge variant="outline" className="text-[10px] font-normal border-amber-500/30 text-amber-600 dark:text-amber-400">
                    Ember Dataset
                  </Badge>
                </CardTitle>
                <CardDescription className="text-xs text-muted-foreground mt-0.5">
                  Dữ liệu tiêu thụ điện năng hàng tháng đo bằng Terawatt-giờ (TWh), thể hiện tốc độ tăng trưởng kinh tế và nhu cầu điện quốc gia.
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="pt-4">
              <TrendChart />
            </CardContent>
          </Card>

          {/* Secondary Charts: Seasonality Pattern & Clustering Overview */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Seasonality Pattern */}
            <Card className="border border-border shadow-xs">
              <CardHeader className="border-b border-border/60 pb-4">
                <CardTitle className="text-base font-semibold text-foreground flex items-center justify-between">
                  <span>Quy luật Tiêu thụ theo Tháng trong Năm</span>
                  <Badge variant="secondary" className="text-[10px] font-normal">
                    Chu kỳ mùa vụ
                  </Badge>
                </CardTitle>
                <CardDescription className="text-xs text-muted-foreground mt-0.5">
                  Nhận diện quy luật sử dụng: Nhu cầu điện tăng vọt vào các tháng hè (T5 - T8) và giảm sâu vào dịp Tết (T1 - T2).
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-4">
                <SeasonalityChart />
              </CardContent>
            </Card>

            {/* Clustering Model Overview */}
            <Card className="border border-border shadow-xs">
              <CardHeader className="border-b border-border/60 pb-4">
                <CardTitle className="text-base font-semibold text-foreground flex items-center justify-between">
                  <span>Phân cụm Đặc trưng Tiêu thụ (Clustering)</span>
                  <Badge variant="outline" className="text-[10px] font-normal border-blue-500/30 text-blue-600 dark:text-blue-400">
                    K-Means Model
                  </Badge>
                </CardTitle>
                <CardDescription className="text-xs text-muted-foreground mt-0.5">
                  Thuật toán phân cụm chia các kỳ tiêu thụ thành 3 nhóm đặc trưng theo mức độ phụ tải và biến động thời tiết.
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-4">
                <ClusteringPieChart />
              </CardContent>
            </Card>
          </div>

          {/* Recent Demand Records Table */}
          <Card className="border border-border shadow-xs">
            <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-border/60 pb-4">
              <div>
                <CardTitle className="text-base font-semibold text-foreground">
                  Dữ liệu Tiêu thụ Gần nhất (Vietnam Electricity Demand)
                </CardTitle>
                <CardDescription className="text-xs text-muted-foreground mt-0.5">
                  Trích xuất các kỳ thu thập mới nhất trong kho dữ liệu (Dataset: vietnam_electricity_demand.csv).
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="xs" className="h-7 text-xs gap-1">
                  <Download className="size-3 text-muted-foreground" />
                  <span>Xuất CSV</span>
                </Button>
              </div>
            </CardHeader>
            <CardContent className="pt-2">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="w-24 text-xs font-semibold">Thời gian</TableHead>
                    <TableHead className="text-xs font-semibold">Quốc gia</TableHead>
                    <TableHead className="text-xs font-semibold text-right">Sản lượng (TWh)</TableHead>
                    <TableHead className="text-xs font-semibold text-right">Tăng trưởng YoY</TableHead>
                    <TableHead className="text-xs font-semibold">Phân loại Cụm</TableHead>
                    <TableHead className="text-xs font-semibold text-center">Trạng thái</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {RECENT_RECORDS.map((record) => (
                    <TableRow key={record.month} className="text-xs">
                      <TableCell className="font-medium font-mono">
                        {record.month}
                      </TableCell>
                      <TableCell>
                        <span className="inline-flex items-center gap-1.5">
                          <span className="size-1.5 rounded-full bg-emerald-500" />
                          {record.country} ({record.iso3})
                        </span>
                      </TableCell>
                      <TableCell className="text-right font-mono font-semibold">
                        {record.value.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {record.growthRateYoY ? (
                          <span
                            className={
                              record.growthRateYoY > 0
                                ? "text-emerald-600 dark:text-emerald-400 font-medium"
                                : "text-rose-600 dark:text-rose-400 font-medium"
                            }
                          >
                            {record.growthRateYoY > 0
                              ? `+${record.growthRateYoY}%`
                              : `${record.growthRateYoY}%`}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={`text-[10px] px-1.5 py-0 h-4 font-normal ${
                            record.cluster === 1
                              ? "bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20"
                              : record.cluster === 3
                              ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20"
                              : "bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/20"
                          }`}
                        >
                          {record.clusterLabel || `Cụm ${record.cluster}`}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge
                          variant="secondary"
                          className="text-[10px] px-1.5 py-0 h-4 font-normal bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-transparent"
                        >
                          Đã xử lý
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
