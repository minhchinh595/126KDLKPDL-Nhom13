import * as React from "react";
import { LucideIcon, Sparkles } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

interface SectionPlaceholderProps {
  title: string;
  subtitle: string;
  badge: string;
  icon: LucideIcon;
  targetObjective: string;
  nextSteps: string[];
}

export function SectionPlaceholder({
  title,
  subtitle,
  badge,
  icon: Icon,
  targetObjective,
  nextSteps,
}: SectionPlaceholderProps) {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-2 border-b border-border/80 pb-5">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Icon className="size-5" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">{title}</h1>
          <Badge variant="outline" className="text-xs">
            {badge}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">{subtitle}</p>
      </div>

      {/* Target Module Objective */}
      <Card className="border border-border/80 bg-muted/20">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Sparkles className="size-4 text-amber-500" />
            <span>Mục tiêu phân hệ (Theo tài liệu đề tài)</span>
          </CardTitle>
          <CardDescription className="text-xs text-muted-foreground">
            {targetObjective}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-1.5 text-xs">
            <p className="font-medium text-foreground">Các bước triển khai tiếp theo:</p>
            <ul className="list-disc list-inside space-y-1 text-muted-foreground">
              {nextSteps.map((step, idx) => (
                <li key={idx}>{step}</li>
              ))}
            </ul>
          </div>
        </CardContent>
      </Card>

      {/* Skeleton Mockup for this Module */}
      <div className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, idx) => (
            <Card key={idx} className="p-4 border border-border/60">
              <Skeleton className="h-4 w-28 mb-3" />
              <Skeleton className="h-8 w-20 mb-2" />
              <Skeleton className="h-3 w-36" />
            </Card>
          ))}
        </div>

        <Card className="p-6 border border-border/60">
          <Skeleton className="h-5 w-48 mb-2" />
          <Skeleton className="h-3.5 w-80 mb-6" />
          <div className="h-64 w-full flex items-end gap-3 pb-2 border-b border-border/40">
            {Array.from({ length: 14 }).map((_, idx) => (
              <div key={idx} className="flex-1 flex flex-col justify-end items-center gap-1.5 h-full">
                <Skeleton
                  className="w-full rounded-t-sm"
                  style={{
                    height: `${30 + ((idx * 23) % 60)}%`,
                  }}
                />
                <Skeleton className="h-2 w-full max-w-[24px]" />
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
