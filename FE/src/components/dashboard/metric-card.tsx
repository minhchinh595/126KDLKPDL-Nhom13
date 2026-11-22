import * as React from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, TrendingDown, Minus, LucideIcon } from "lucide-react";

interface MetricCardProps {
  title: string;
  value: string | number;
  unit?: string;
  trend?: number;
  trendLabel?: string;
  icon: LucideIcon;
  variant?: "default" | "amber" | "blue" | "emerald" | "purple";
  description?: string;
}

const VARIANT_STYLES = {
  default: {
    iconBg: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
    accent: "text-slate-900 dark:text-slate-100",
  },
  amber: {
    iconBg: "bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300",
    accent: "text-amber-600 dark:text-amber-400",
  },
  blue: {
    iconBg: "bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300",
    accent: "text-blue-600 dark:text-blue-400",
  },
  emerald: {
    iconBg: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300",
    accent: "text-emerald-600 dark:text-emerald-400",
  },
  purple: {
    iconBg: "bg-purple-100 text-purple-700 dark:bg-purple-950/60 dark:text-purple-300",
    accent: "text-purple-600 dark:text-purple-400",
  },
};

export function MetricCard({
  title,
  value,
  unit,
  trend,
  trendLabel = "so với cùng kỳ",
  icon: Icon,
  variant = "default",
  description,
}: MetricCardProps) {
  const styles = VARIANT_STYLES[variant];

  return (
    <Card className="p-4 border border-border shadow-xs hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between pb-1">
        <span className="text-xs font-medium text-muted-foreground truncate" title={title}>
          {title}
        </span>
        <div className={`flex size-8 shrink-0 items-center justify-center rounded-lg ${styles.iconBg}`}>
          <Icon className="size-4" />
        </div>
      </div>

      <div className="space-y-1.5 pt-1">
        <div className="flex items-baseline gap-1.5">
          <span className="text-2xl font-bold tracking-tight text-foreground font-mono">
            {value}
          </span>
          {unit && (
            <span className="text-xs font-semibold text-muted-foreground uppercase">
              {unit}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 flex-wrap text-xs">
          {typeof trend === "number" && (
            <Badge
              variant={trend > 0 ? "secondary" : trend < 0 ? "destructive" : "outline"}
              className={`h-5 gap-1 px-1.5 text-[11px] font-medium ${
                trend > 0
                  ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                  : trend < 0
                  ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20"
                  : ""
              }`}
            >
              {trend > 0 ? (
                <TrendingUp className="size-3" />
              ) : trend < 0 ? (
                <TrendingDown className="size-3" />
              ) : (
                <Minus className="size-3" />
              )}
              <span>{trend > 0 ? `+${trend}%` : `${trend}%`}</span>
            </Badge>
          )}
          {description ? (
            <span className="text-[11px] text-muted-foreground truncate">{description}</span>
          ) : trendLabel ? (
            <span className="text-[11px] text-muted-foreground truncate">{trendLabel}</span>
          ) : null}
        </div>
      </div>
    </Card>
  );
}
