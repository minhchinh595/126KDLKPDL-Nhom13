import { DemandApiError, resolveApiBase } from "./demand-api";

export type AnalyticsEndpoint = "/api/dashboard/overview" | "/api/electricity/demand/statistics" | "/api/analysis/summary" | "/api/analysis/trend" | "/api/analysis/seasonality" | "/api/analysis/correlation" | "/api/analysis/distribution" | "/api/analysis/scatter";
export type AnalyticsParams = Record<string, string | number>;
export function rangeParams(points: { date: string }[]): AnalyticsParams {
  if (!points.length) return {};
  const sorted = [...points].map(point => point.date).sort();
  const next = new Date(`${sorted.at(-1)}T12:00:00Z`); next.setUTCDate(next.getUTCDate() + 1);
  const exclusiveEnd = next.toISOString().slice(0, 10);
  return { start_at: `${sorted[0]}T00:00:00+10:00`, end_at: `${exclusiveEnd}T00:00:00+10:00` };
}

export interface SummaryResult { metric: string; interval: string; unit: string; sample_count: number; start_date: string | null; end_date: string | null; mean: number | null; median: number | null; minimum: number | null; maximum: number | null }
export interface DemandStatisticsResult { metric: "demand"; interval: "1d"; unit: "MW"; count: number; mean: number | null; minimum: number | null; maximum: number | null; coverage: Record<string, unknown> }
export interface TrendResult { metric: string; unit: string; view: "day" | "week" | "month"; aggregation: string; records: { period: string; value: number | null; sample_count: number; weighted_sample_count: number | null; expected_days: number; coverage_fraction: number | null }[] }
export interface SeasonalityResult { metric: string; unit: string; method: string; limitation: string; records: { weekday: number; count: number; mean: number | null }[] }
export interface CorrelationResult { metrics: Record<string, { unit: string | null }>; alignment: string; sample_dates: number; matrix: Record<string, Record<string, number | null>>; pair_counts: Record<string, Record<string, number>> }
export interface DistributionResult { metric: string; interval: string; unit: string | null; sample_count: number; bins: { start: number; end: number; count: number }[] }
export interface ScatterResult { x: { metric: string; unit: string | null; interval: string | null }; y: { metric: string; unit: string | null; interval: string | null }; sample_count: number; points: { date: string; x: number; y: number }[] }
export interface DashboardResult { dataset_name: string; dataset_status: string; total_observations: number; latest_daily_demand_mw: number | null; average_daily_demand_mw: number | null; minimum_daily_demand_mw: number | null; maximum_daily_demand_mw: number | null; latest_renewable_proportion_percent: number | null; latest_price_per_mwh: number | null; latest_data_timestamp: string | null; timezone: "Australia/Brisbane" }

const isoWeekdayNames = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"];
export function seasonalityWeekdayLabel(weekday: number): string { return isoWeekdayNames[weekday - 1] ?? `Ngày ${weekday}`; }
export function seasonalityWeekdayRows(records: SeasonalityResult["records"]): SeasonalityResult["records"] {
  const byWeekday = new Map(records.map(row => [row.weekday, row]));
  return Array.from({ length: 7 }, (_, index) => byWeekday.get(index + 1) ?? { weekday: index + 1, count: 0, mean: null });
}

const invalid = (): never => { throw new Error("Kết quả API NEM không đúng cấu trúc mong đợi."); };
const object = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : invalid();
const finite = (value: unknown, nullable = false) => { if (nullable && value === null) return; if (typeof value !== "number" || !Number.isFinite(value)) invalid(); };
const count = (value: unknown) => { finite(value); if (!Number.isSafeInteger(value) || (value as number) < 0) invalid(); };
const metricUnits: Record<string, string> = { demand: "MW", generation_renewable: "MW", price: "$/MWh", renewable_proportion: "%", demand_energy: "MWh" };
function validateBase(input: unknown) { const data = object(input); if (typeof data.metric !== "string" || typeof data.unit !== "string" || metricUnits[data.metric] !== data.unit) invalid(); return data; }
function validPeriod(value: unknown) {
  if (typeof value !== "string") return false;
  const monthOnly = /^(\d{4})-(\d{2})$/.exec(value);
  if (monthOnly) return Number(monthOnly[2]) >= 1 && Number(monthOnly[2]) <= 12;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}
export function parseSummary(input: unknown): SummaryResult {
  const data = validateBase(input); count(data.sample_count);
  for (const key of ["mean", "median", "minimum", "maximum"]) finite(data[key], true);
  for (const key of ["start_date", "end_date"]) if (data[key] !== null && !validPeriod(data[key])) invalid();
  if (data.interval !== "1d") invalid(); return data as unknown as SummaryResult;
}
export function parseDemandStatistics(input: unknown): DemandStatisticsResult {
  const data = object(input);
  if (data.metric !== "demand" || data.interval !== "1d" || data.unit !== "MW" || !data.coverage || typeof data.coverage !== "object" || Array.isArray(data.coverage)) invalid();
  count(data.count); finite(data.mean, true); finite(data.minimum, true); finite(data.maximum, true);
  return data as unknown as DemandStatisticsResult;
}
export function parseTrend(input: unknown): TrendResult {
  const data = validateBase(input); if (!["day", "week", "month"].includes(String(data.view)) || typeof data.aggregation !== "string" || !Array.isArray(data.records)) invalid();
  for (const raw of data.records as unknown[]) { const row = object(raw); if (!validPeriod(row.period)) invalid(); finite(row.value, true); count(row.sample_count); if (row.weighted_sample_count !== null) count(row.weighted_sample_count); count(row.expected_days); finite(row.coverage_fraction, true); }
  return data as unknown as TrendResult;
}
export function parseSeasonality(input: unknown): SeasonalityResult {
  const data = validateBase(input); if (typeof data.method !== "string" || typeof data.limitation !== "string" || !Array.isArray(data.records)) invalid();
  for (const raw of data.records as unknown[]) { const row = object(raw); count(row.weekday); count(row.count); finite(row.mean, true); if ((row.weekday as number) < 1 || (row.weekday as number) > 7) invalid(); }
  return data as unknown as SeasonalityResult;
}
export function parseCorrelation(input: unknown): CorrelationResult {
  const data = object(input), metrics = object(data.metrics), matrix = object(data.matrix), pairCounts = object(data.pair_counts);
  if (typeof data.alignment !== "string" || !Number.isSafeInteger(data.sample_dates) || !Object.keys(metrics).length) invalid();
  for (const [name, metadata] of Object.entries(metrics)) { const unit = object(metadata).unit; if (!name || (unit !== null && typeof unit !== "string")) invalid(); const row = object(matrix[name]), counts = object(pairCounts[name]); for (const other of Object.keys(metrics)) { finite(row[other], true); count(counts[other]); } }
  return data as unknown as CorrelationResult;
}
export function parseDistribution(input: unknown): DistributionResult {
  const data = object(input); const expectedUnit = typeof data.metric === "string" ? metricUnits[data.metric] : undefined;
  if (!expectedUnit || typeof data.interval !== "string" || !Array.isArray(data.bins)) invalid(); count(data.sample_count);
  if (data.unit === null ? data.sample_count !== 0 : data.unit !== expectedUnit) invalid();
  let sum = 0; for (const raw of data.bins as unknown[]) { const bin = object(raw); finite(bin.start); finite(bin.end); count(bin.count); if ((bin.start as number) > (bin.end as number)) invalid(); sum += bin.count as number; }
  if (sum !== data.sample_count) invalid(); return data as unknown as DistributionResult;
}
export function parseScatter(input: unknown): ScatterResult {
  const data = object(input), x = object(data.x), y = object(data.y); count(data.sample_count);
  for (const metric of [x, y]) if (typeof metric.metric !== "string") invalid();
  if (!Array.isArray(data.points)) invalid(); for (const raw of data.points as unknown[]) { const point = object(raw); if (typeof point.date !== "string") invalid(); finite(point.x); finite(point.y); }
  return data as unknown as ScatterResult;
}
export function parseDashboard(input: unknown): DashboardResult {
  const data = object(input);
  if (data.dataset_name !== "Open Electricity NEM" || typeof data.dataset_status !== "string" || data.timezone !== "Australia/Brisbane") invalid();
  count(data.total_observations); for (const key of ["latest_daily_demand_mw", "average_daily_demand_mw", "minimum_daily_demand_mw", "maximum_daily_demand_mw", "latest_renewable_proportion_percent", "latest_price_per_mwh"]) finite(data[key], true);
  if (data.latest_data_timestamp !== null && (typeof data.latest_data_timestamp !== "string" || !Number.isFinite(Date.parse(data.latest_data_timestamp)))) invalid();
  return data as unknown as DashboardResult;
}
export function analyticsPath(endpoint: AnalyticsEndpoint, params: AnalyticsParams = {}) {
  const query = new URLSearchParams(Object.entries(params).sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => [key, String(value)]));
  return endpoint + (query.size ? `?${query}` : "");
}
export async function fetchAnalytics<T>(endpoint: AnalyticsEndpoint, params: AnalyticsParams, parse: (value: unknown) => T, { signal, baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001", timeoutMs = 15000 }: { signal?: AbortSignal; baseUrl?: string; timeoutMs?: number } = {}): Promise<T> {
  const controller = new AbortController(); const abort = () => controller.abort();
  if (signal?.aborted) controller.abort(); signal?.addEventListener("abort", abort, { once: true });
  let timedOut = false; const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const response = await fetch(resolveApiBase(baseUrl) + analyticsPath(endpoint, params), { credentials: "include", cache: "no-store", headers: { Accept: "application/json" }, signal: controller.signal });
    if (!response.ok) {
      let detail: unknown; try { detail = (await response.json()).detail; } catch { /* status remains useful */ }
      const message = typeof detail === "string" ? detail : response.status === 503 ? "Dịch vụ phân tích hoặc dữ liệu NEM chưa sẵn sàng." : `Không tải được kết quả phân tích (HTTP ${response.status}).`;
      throw new DemandApiError(response.status, message, detail);
    }
    return parse(await response.json());
  } catch (error) {
    if (signal?.aborted) throw error; if (timedOut) throw new Error("API phân tích phản hồi quá lâu. Vui lòng thử lại.");
    if (error instanceof TypeError) throw new Error("Không kết nối được API phân tích. Hãy kiểm tra Gateway."); if (error instanceof SyntaxError) throw new Error("API phân tích không trả về JSON hợp lệ."); throw error;
  } finally { clearTimeout(timer); signal?.removeEventListener("abort", abort); }
}
