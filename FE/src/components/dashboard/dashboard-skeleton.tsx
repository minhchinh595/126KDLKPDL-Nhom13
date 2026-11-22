import * as React from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardHeader, CardContent } from "@/components/ui/card";

export function DashboardSkeleton() {
  return (
    <div className="space-y-6 animate-in fade-in-50 duration-300" data-testid="dashboard-skeleton">
      {/* Page Header Skeleton */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2">
          <Skeleton className="h-8 w-72 sm:w-96" />
          <Skeleton className="h-4 w-96 max-w-full" />
        </div>
        <div className="flex items-center gap-2.5">
          <Skeleton className="h-9 w-32 rounded-lg" />
          <Skeleton className="h-9 w-24 rounded-lg" />
        </div>
      </div>

      {/* 4 KPI Metric Cards Skeleton */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, idx) => (
          <Card key={idx} className="p-4 border border-border/80 shadow-xs">
            <div className="flex items-center justify-between pb-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="size-8 rounded-lg" />
            </div>
            <div className="space-y-2 pt-1">
              <Skeleton className="h-8 w-28" />
              <div className="flex items-center gap-2">
                <Skeleton className="h-4 w-14 rounded-full" />
                <Skeleton className="h-3 w-28" />
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Main Chart Card Skeleton (Time-series Demand) */}
      <Card className="border border-border/80 shadow-xs">
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-border/60 pb-4">
          <div className="space-y-1.5">
            <Skeleton className="h-5 w-64" />
            <Skeleton className="h-3.5 w-80" />
          </div>
          <div className="flex items-center gap-2">
            <Skeleton className="h-8 w-20 rounded-md" />
            <Skeleton className="h-8 w-20 rounded-md" />
            <Skeleton className="h-8 w-20 rounded-md" />
          </div>
        </CardHeader>
        <CardContent className="pt-6">
          <div className="space-y-4">
            {/* Chart Grid Lines Mockup */}
            <div className="h-72 w-full flex items-end gap-2 pt-6 pb-2 px-2 border-b border-border/40">
              {Array.from({ length: 18 }).map((_, i) => (
                <div key={i} className="flex-1 flex flex-col justify-end items-center gap-1.5 h-full">
                  <Skeleton
                    className="w-full rounded-t-sm"
                    style={{
                      height: `${25 + ((i * 17) % 65)}%`,
                    }}
                  />
                  <Skeleton className="h-2 w-full max-w-[20px]" />
                </div>
              ))}
            </div>
            <div className="flex justify-between items-center pt-2">
              <div className="flex items-center gap-4">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-3 w-28" />
              </div>
              <Skeleton className="h-3 w-36" />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Secondary Row Skeleton: Seasonal Pattern & Clustering */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Seasonal Pattern Skeleton */}
        <Card className="border border-border/80 shadow-xs">
          <CardHeader className="border-b border-border/60 pb-4">
            <div className="space-y-1.5">
              <Skeleton className="h-5 w-52" />
              <Skeleton className="h-3.5 w-72" />
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="h-60 w-full flex items-end gap-3 pb-2 border-b border-border/40">
              {Array.from({ length: 12 }).map((_, i) => (
                <div key={i} className="flex-1 flex flex-col justify-end items-center gap-1 h-full">
                  <Skeleton
                    className="w-full rounded-t-sm"
                    style={{
                      height: `${35 + ((i >= 4 && i <= 7 ? 50 : 20) + (i % 3) * 5)}%`,
                    }}
                  />
                  <Skeleton className="h-2.5 w-4" />
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between pt-3">
              <Skeleton className="h-3 w-40" />
              <Skeleton className="h-3 w-28" />
            </div>
          </CardContent>
        </Card>

        {/* Clustering Segmentation Skeleton */}
        <Card className="border border-border/80 shadow-xs">
          <CardHeader className="border-b border-border/60 pb-4">
            <div className="space-y-1.5">
              <Skeleton className="h-5 w-56" />
              <Skeleton className="h-3.5 w-64" />
            </div>
          </CardHeader>
          <CardContent className="pt-6 space-y-4">
            <div className="flex items-center justify-center py-2">
              <Skeleton className="size-36 rounded-full" />
            </div>
            <div className="space-y-2.5 pt-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="flex items-center justify-between p-2 rounded-lg border border-border/50">
                  <div className="flex items-center gap-2">
                    <Skeleton className="size-3 rounded-full" />
                    <Skeleton className="h-4 w-44" />
                  </div>
                  <Skeleton className="h-4 w-16" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent Records Table Skeleton */}
      <Card className="border border-border/80 shadow-xs">
        <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-border/60 pb-4">
          <div className="space-y-1.5">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-3.5 w-64" />
          </div>
          <Skeleton className="h-8 w-28 rounded-md" />
        </CardHeader>
        <CardContent className="pt-4">
          <div className="space-y-3">
            {/* Table Header Skeleton */}
            <div className="flex items-center justify-between border-b border-border/60 pb-2">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-20" />
            </div>
            {/* Table Rows Skeleton */}
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center justify-between py-2 border-b border-border/40 last:border-0">
                <Skeleton className="h-4 w-16" />
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-4 w-16 rounded-full" />
                <Skeleton className="h-6 w-18 rounded-md" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
