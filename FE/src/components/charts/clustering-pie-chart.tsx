"use client";

import * as React from "react";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
} from "recharts";
import { CLUSTERING_SUMMARY } from "@/lib/electricity-data";
import { useIsMounted } from "@/hooks/use-mounted";

export function ClusteringPieChart() {
  const mounted = useIsMounted();

  if (!mounted) {
    return (
      <div className="h-60 w-full flex items-center justify-center bg-muted/20 rounded-lg text-sm text-muted-foreground animate-pulse">
        Đang khởi tạo biểu đồ phân cụm...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="h-44 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Tooltip
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  const data = payload[0].payload as (typeof CLUSTERING_SUMMARY)[0];
                  return (
                    <div className="rounded-lg border border-border bg-popover p-2.5 shadow-md text-xs space-y-1">
                      <p className="font-semibold text-foreground">{data.name}</p>
                      <p className="font-mono text-xs">
                        Số lượng: <strong>{data.count} tháng</strong> ({data.percentage}%)
                      </p>
                      <p className="text-[11px] text-muted-foreground">
                        Nhu cầu TB: <strong>{data.avgDemand} TWh</strong>
                      </p>
                    </div>
                  );
                }
                return null;
              }}
            />
            <Pie
              data={CLUSTERING_SUMMARY}
              cx="50%"
              cy="50%"
              innerRadius={45}
              outerRadius={70}
              paddingAngle={4}
              dataKey="count"
            >
              {CLUSTERING_SUMMARY.map((entry) => (
                <Cell key={`cluster-${entry.clusterId}`} fill={entry.color} strokeWidth={1} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>

      {/* Cluster Legend List */}
      <div className="space-y-2">
        {CLUSTERING_SUMMARY.map((item) => (
          <div
            key={item.clusterId}
            className="flex items-center justify-between text-xs p-2 rounded-lg border border-border/60 bg-muted/20 hover:bg-muted/40 transition-colors"
          >
            <div className="flex items-center gap-2 min-w-0">
              <span
                className="size-2.5 rounded-full shrink-0"
                style={{ backgroundColor: item.color }}
              />
              <span className="font-medium text-foreground truncate">
                {item.name.split(":")[0]}: {item.name.split(":")[1]}
              </span>
            </div>
            <div className="flex items-center gap-2 shrink-0 font-mono text-[11px] text-muted-foreground">
              <span>{item.count} tháng</span>
              <span className="font-semibold text-foreground">({item.percentage}%)</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
