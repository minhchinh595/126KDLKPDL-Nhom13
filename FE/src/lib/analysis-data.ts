export interface DemandPoint { month: string; value: number }
export type Granularity = "month" | "quarter" | "year";
export type Variable = "demand" | "previousMonth" | "previousYear" | "monthNumber";
export const VARIABLES: Record<Variable, { label: string; unit: string }> = {
  demand: { label: "Tiêu thụ hiện tại", unit: "TWh" },
  previousMonth: { label: "Tiêu thụ tháng trước", unit: "TWh" },
  previousYear: { label: "Tiêu thụ cùng kỳ năm trước", unit: "TWh" },
  monthNumber: { label: "Tháng trong năm", unit: "tháng" },
};

export const mean = (values: number[]) => values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
export function previousYearMonth(month: string) {
  return `${Number(month.slice(0, 4)) - 1}${month.slice(4)}`;
}
function previousMonth(month: string) {
  const year = Number(month.slice(0, 4));
  const m = Number(month.slice(5));
  return `${m === 1 ? year - 1 : year}-${String(m === 1 ? 12 : m - 1).padStart(2, "0")}`;
}

export function aggregateDemand(selected: DemandPoint[], all: DemandPoint[], granularity: Granularity) {
  const lookup = new Map(all.map(p => [p.month, p.value]));
  const groups = new Map<string, DemandPoint[]>();
  selected.forEach(p => {
    const key = granularity === "year" ? p.month.slice(0, 4) : granularity === "quarter"
      ? `${p.month.slice(0, 4)}-Q${Math.ceil(Number(p.month.slice(5)) / 3)}` : p.month;
    groups.set(key, [...(groups.get(key) ?? []), p]);
  });
  return [...groups].map(([period, points]) => {
    const total = points.reduce((sum, p) => sum + p.value, 0);
    const prior = points.map(p => lookup.get(previousYearMonth(p.month)));
    const comparable = prior.every(v => v !== undefined);
    const previous = comparable ? (prior as number[]).reduce((a, b) => a + b, 0) : null;
    return { period, total, count: points.length, average: total / points.length,
      previous, growth: previous !== null && previous !== 0 ? (total / previous - 1) * 100 : null };
  });
}

export function movingAverage(selected: DemandPoint[], all: DemandPoint[], window: number) {
  const lookup = new Map(all.map(p => [p.month, p.value]));
  return selected.map(p => {
    const values: number[] = [];
    let month = p.month;
    for (let i = 0; i < window; i++) {
      const value = lookup.get(month);
      if (value === undefined) break;
      values.push(value);
      month = previousMonth(month);
    }
    return { ...p, movingAverage: values.length === window ? mean(values) : null };
  });
}

export function seasonalPattern(points: DemandPoint[]) {
  return Array.from({ length: 12 }, (_, i) => {
    const values = points.filter(p => Number(p.month.slice(5)) === i + 1).map(p => p.value);
    return { month: `T${i + 1}`, count: values.length, average: mean(values),
      min: values.length ? Math.min(...values) : null, max: values.length ? Math.max(...values) : null };
  });
}

export function pairedObservations(selected: DemandPoint[], all: DemandPoint[], x: Variable, y: Variable) {
  const lookup = new Map(all.map(p => [p.month, p.value]));
  function value(p: DemandPoint, variable: Variable) {
    if (variable === "demand") return p.value;
    if (variable === "monthNumber") return Number(p.month.slice(5));
    return lookup.get(variable === "previousMonth" ? previousMonth(p.month) : previousYearMonth(p.month));
  }
  return selected.flatMap(p => {
    const vx = value(p, x), vy = value(p, y);
    return vx !== undefined && vy !== undefined ? [{ month: p.month, x: vx, y: vy }] : [];
  });
}

export function pearson(x: number[], y: number[]) {
  if (x.length < 3 || x.length !== y.length) return null;
  const mx = mean(x)!, my = mean(y)!;
  let numerator = 0, dx = 0, dy = 0;
  x.forEach((v, i) => { numerator += (v - mx) * (y[i] - my); dx += (v - mx) ** 2; dy += (y[i] - my) ** 2; });
  return dx && dy ? Math.max(-1, Math.min(1, numerator / Math.sqrt(dx * dy))) : null;
}
function ranks(values: number[]) {
  const sorted = values.map((value, index) => ({ value, index })).sort((a, b) => a.value - b.value);
  const result = Array<number>(values.length);
  for (let i = 0; i < sorted.length;) {
    let end = i + 1;
    while (end < sorted.length && sorted[end].value === sorted[i].value) end++;
    for (let j = i; j < end; j++) result[sorted[j].index] = (i + 1 + end) / 2;
    i = end;
  }
  return result;
}
export function spearman(x: number[], y: number[]) { return pearson(ranks(x), ranks(y)); }

export const DEMAND_LEVELS = [
  { key: "low", label: "Thấp", range: "Dưới 21 TWh", color: "#10b981" },
  { key: "medium", label: "Trung bình", range: "21 – 27 TWh", color: "#3b82f6" },
  { key: "high", label: "Cao", range: "Trên 27 TWh", color: "#f59e0b" },
] as const;
export function demandLevel(value: number) { return value < 21 ? "low" : value > 27 ? "high" : "medium"; }

export function filterDemand(points: DemandPoint[], start: string, end: string) {
  if (!start || !end || start > end) return [];
  return points.filter(p => p.month >= start && p.month <= end);
}

export function monthlyChanges(selected: DemandPoint[], all: DemandPoint[]) {
  const lookup = new Map(all.map(p => [p.month, p.value]));
  const growth = (current: number, previous: number | undefined) => previous === undefined || previous === 0 ? null : (current / previous - 1) * 100;
  return selected.map(p => ({ ...p,
    previous: lookup.get(previousYearMonth(p.month)) ?? null,
    yoy: growth(p.value, lookup.get(previousYearMonth(p.month))),
    mom: growth(p.value, lookup.get(previousMonth(p.month))),
    level: demandLevel(p.value),
  }));
}

export function summarizeDemand(selected: DemandPoint[], all: DemandPoint[]) {
  const sorted = [...selected].sort((a, b) => a.month.localeCompare(b.month));
  const latest = monthlyChanges(sorted.slice(-1), all)[0] ?? null;
  return {
    latest,
    count: selected.length,
    total: selected.reduce((sum, p) => sum + p.value, 0),
    average: mean(selected.map(p => p.value)),
    peak: selected.length ? selected.reduce((a, b) => a.value >= b.value ? a : b) : null,
    low: selected.length ? selected.reduce((a, b) => a.value <= b.value ? a : b) : null,
    levels: DEMAND_LEVELS.map(level => {
      const points = selected.filter(p => demandLevel(p.value) === level.key);
      return { ...level, count: points.length, percentage: selected.length ? points.length / selected.length * 100 : 0 };
    }),
  };
}
