import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

export function PageHeading({ title, description, icon: Icon, eyebrow = "Electricity Analytics", actions, compact = false }: { title: string; description: string; icon: LucideIcon; eyebrow?: string; actions?: ReactNode; compact?: boolean }) {
  return <div className={`flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between ${compact ? "" : "pb-2"}`}>
    <div className="flex gap-3 min-w-0">
      <div className={`hidden sm:flex shrink-0 items-center justify-center rounded-xl border border-primary/15 bg-primary/10 text-primary ${compact ? "size-10" : "size-12"}`}><Icon className="size-5" /></div>
      <div className={`min-w-0 ${compact ? "space-y-0.5" : "space-y-1.5"}`}><p className="text-[10px] uppercase tracking-[0.18em] font-semibold text-primary">{eyebrow}</p><h1 className={`${compact ? "text-xl sm:text-2xl" : "text-2xl sm:text-3xl"} font-semibold tracking-tight text-foreground`}>{title}</h1><p className={`max-w-2xl leading-relaxed text-muted-foreground ${compact ? "text-xs" : "text-sm"}`}>{description}</p></div>
    </div>
    {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
  </div>;
}
