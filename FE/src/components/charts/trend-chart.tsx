"use client";

import * as React from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { RAW_DEMAND_SERIES } from "@/lib/electricity-data";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useIsMounted } from "@/hooks/use-mounted";

export function TrendChart() {
  const mounted = useIsMounted();
  const [filterPeriod, setFilterPeriod] = React.useState<"all" | "recent" | "mid" | "early">("all");

  const filteredData = React.useMemo(() => {
    switch (filterPeriod) {
      case "recent":
        return RAW_DEMAND_SERIES.filter((d) => d.month >= "2024-01");
      case "mid":
        return RAW_DEMAND_SERIES.filter((d) => d.month >= "2021-01" && d.month <= "2023-12");
      case "early":
        return RAW_DEMAND_SERIES.filter((d) => d.month <= "2020-12");
      default:
        return RAW_DEMAND_SERIES;
    }
  }, [filterPeriod]);

  if (!mounted) {
    return (
      <div className="h-72 w-full flex items-center justify-center bg-muted/20 rounded-lg text-sm text-muted-foreground animate-pulse">
        Đang khởi tạo biểu đồ xu hướng...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-xs bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/20">
            Nhu cầu Điện năng (TWh)
          </Badge>
          <span className="text-xs text-muted-foreground hidden sm:inline">
            {filteredData.length} kỳ dữ liệu
          </span>
        </div>

        {/* Filter controls */}
        <div className="flex items-center gap-1 bg-muted/50 p-0.5 rounded-lg border border-border/60 text-xs">
          <Button
            size="xs"
            variant={filterPeriod === "all" ? "default" : "ghost"}
            onClick={() => setFilterPeriod("all")}
            className="text-xs px-2.5 h-6"
          >
            2019 - 2026
          </Button>
          <Button
            size="xs"
            variant={filterPeriod === "recent" ? "default" : "ghost"}
            onClick={() => setFilterPeriod("recent")}
            className="text-xs px-2.5 h-6"
          >
            2024 - 2026
          </Button>
          <Button
            size="xs"
            variant={filterPeriod === "mid" ? "default" : "ghost"}
            onClick={() => setFilterPeriod("mid")}
            className="text-xs px-2.5 h-6"
          >
            2021 - 2023
          </Button>
          <Button
            size="xs"
            variant={filterPeriod === "early" ? "default" : "ghost"}
            onClick={() => setFilterPeriod("early")}
            className="text-xs px-2.5 h-6"
          >
            2019 - 2020
          </Button>
        </div>
      </div>

      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={filteredData} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
            <defs>
              <linearGradient id="electricityGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#f59e0b" stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="currentColor" className="text-border/60" />
            <XAxis
              dataKey="month"
              tickLine={false}
              axisLine={false}
              stroke="currentColor"
              className="text-muted-foreground text-[11px]"
              interval={filterPeriod === "all" ? 6 : 2}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              stroke="currentColor"
              className="text-muted-foreground text-[11px]"
              domain={[14, 35]}
              unit=" TWh"
            />
            <Tooltip
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  const data = payload[0].payload;
                  return (
                    <div className="rounded-lg border border-border bg-popover p-2.5 shadow-md text-xs space-y-1">
                      <p className="font-semibold text-foreground">Tháng: {data.month}</p>
                      <p className="text-amber-600 dark:text-amber-400 font-mono font-medium">
                        Nhu cầu: {data.value} TWh
                      </p>
                      <p className="text-[10px] text-muted-foreground">Việt Nam • Metric: Demand</p>
                    </div>
                  );
                }
                return null;
              }}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="#f59e0b"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#electricityGradient)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
