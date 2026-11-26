export interface DemandPoint { date: string; value: number }
export type Granularity = "day" | "week" | "month";
export type Variable = "demand" | "price" | "demand_energy" | "generation_renewable" | "renewable_proportion";

export function filterDemand(points: DemandPoint[], start: string, end: string) {
  if (!start || !end || start > end) return [];
  return points.filter(point => point.date >= start && point.date <= end);
}

export function summarizeDemand(points: DemandPoint[]) {
  const sorted = [...points].sort((a, b) => a.date.localeCompare(b.date));
  const values = points.map(point => point.value);
  return {
    latest: sorted.at(-1) ?? null,
    count: values.length,
    mean: values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null,
    minimum: values.length ? Math.min(...values) : null,
    maximum: values.length ? Math.max(...values) : null,
  };
}

export function periodKey(day: string, granularity: Granularity) {
  const date = new Date(`${day}T12:00:00Z`);
  if (granularity === "day") return day;
  if (granularity === "month") return day.slice(0, 7);
  const weekday = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - weekday);
  return date.toISOString().slice(0, 10);
}

export function aggregateDemand(points: DemandPoint[], granularity: Granularity) {
  const groups = new Map<string, number[]>();
  for (const point of points) groups.set(periodKey(point.date, granularity), [...(groups.get(periodKey(point.date, granularity)) ?? []), point.value]);
  return [...groups].sort(([a], [b]) => a.localeCompare(b)).map(([period, values]) => ({
    period, sample_count: values.length, mean: values.reduce((sum, value) => sum + value, 0) / values.length,
    minimum: Math.min(...values), maximum: Math.max(...values),
  }));
}
