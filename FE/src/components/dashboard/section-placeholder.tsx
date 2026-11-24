import * as React from "react";
import { LucideIcon, Sparkles } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

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

    </div>
  );
}
