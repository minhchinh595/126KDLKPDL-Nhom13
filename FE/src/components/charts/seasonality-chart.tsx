"use client";

import * as React from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
} from "recharts";
import { MONTHLY_PATTERNS } from "@/lib/electricity-data";
import { useIsMounted } from "@/hooks/use-mounted";

export function SeasonalityChart() {
  const mounted = useIsMounted();

  if (!mounted) {
    return (
      <div className="h-60 w-full flex items-center justify-center bg-muted/20 rounded-lg text-sm text-muted-foreground animate-pulse">
        Đang khởi tạo biểu đồ chu kỳ mùa...
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Nhu cầu điện trung bình từng tháng (2019-2026)</span>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="size-2.5 rounded-xs bg-amber-500" />
            Đỉnh mùa hè
          </span>
          <span className="flex items-center gap-1">
            <span className="size-2.5 rounded-xs bg-blue-500" />
            Bình thường
          </span>
          <span className="flex items-center gap-1">
            <span className="size-2.5 rounded-xs bg-emerald-500" />
            Thấp điểm
          </span>
        </div>
      </div>

      <div className="h-60 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={MONTHLY_PATTERNS} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="currentColor" className="text-border/60" />
            <XAxis
              dataKey="monthName"
              tickLine={false}
              axisLine={false}
              stroke="currentColor"
              className="text-muted-foreground text-xs font-medium"
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              stroke="currentColor"
              className="text-muted-foreground text-xs"
              domain={[16, 28]}
              unit=" TWh"
            />
            <Tooltip
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  const data = payload[0].payload;
                  const isPeak = data.monthIndex >= 5 && data.monthIndex <= 8;
                  const isLow = data.monthIndex <= 2;
                  return (
                    <div className="rounded-lg border border-border bg-popover p-2.5 shadow-md text-xs space-y-1">
                      <p className="font-semibold text-foreground">
                        {data.monthName} (Tháng {data.monthIndex})
                      </p>
                      <p className="font-mono font-medium text-amber-600 dark:text-amber-400">
                        TB: {data.avgDemand} TWh
                      </p>
                      <p className="text-[10px] text-muted-foreground">
                        Biên độ: {data.minDemand} - {data.maxDemand} TWh
                      </p>
                      <p className="text-[10px] font-semibold text-foreground/80 pt-0.5">
                        {isPeak
                          ? "🔥 Mùa cao điểm nắng nóng"
                          : isLow
                          ? "❄️ Thấp điểm / Nghỉ Tết"
                          : "⚡ Giai đoạn ổn định"}
                      </p>
                    </div>
                  );
                }
                return null;
              }}
            />
            <Bar dataKey="avgDemand" radius={[4, 4, 0, 0]}>
              {MONTHLY_PATTERNS.map((entry) => {
                let color = "#3b82f6";
                if (entry.monthIndex >= 5 && entry.monthIndex <= 8) {
                  color = "#f59e0b";
                } else if (entry.monthIndex <= 2) {
                  color = "#10b981";
                }
                return <Cell key={`cell-${entry.monthIndex}`} fill={color} />;
              })}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
