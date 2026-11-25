import { DemandApiError, resolveApiBase } from "./demand-api";

export type AnalyticsEndpoint = "/api/dashboard/overview" | "/api/analysis/summary" | "/api/analysis/trend" | "/api/analysis/seasonality" | "/api/analysis/correlation" | "/api/analysis/distribution";
export type AnalyticsParams = Record<string, string | number>;
export function rangeParams(points: { month: string }[]): AnalyticsParams {
  return points.length ? { start_month: points[0].month, end_month: points[points.length - 1].month } : {};
}
export interface SummaryResult { unit: string; count: number; start_month: string | null; end_month: string | null; mean: number | null; median: number | null; min: number | null; max: number | null }
export interface TrendResult { unit: string; method: string; window_months: number; records: { month: string; value: number; trend: number | null }[] }
export interface SeasonalityResult { unit: string; method: string; records: { month_number: number; count: number; mean: number | null; median: number | null; min: number | null; max: number | null }[] }
export const CORRELATION_FEATURES = ["demand", "previous_month", "previous_year"] as const;
export type CorrelationFeature = typeof CORRELATION_FEATURES[number];
export interface CorrelationResult { unit: string; method: string; features: CorrelationFeature[]; matrix: Record<CorrelationFeature, Record<CorrelationFeature, number | null>>; pair_counts: Record<CorrelationFeature, Record<CorrelationFeature, number>> }
export interface DistributionResult { unit: string; count: number; bins: { start: number; end: number; count: number }[] }
export interface DashboardResult { unit: string; record_count: number; start_month: string | null; latest_month: string | null; mean_demand_twh: number | null; minimum_demand_twh: number | null; maximum_demand_twh: number | null; latest_demand_twh: number | null; change_from_previous_month_pct: number | null; dataset_count: number; model_run_count: number; data_updated_at: string | null }

function invalid(): never { throw new Error("Kết quả API phân tích không đúng cấu trúc mong đợi."); }
function object(value: unknown): Record<string, unknown> { if (!value || typeof value !== "object" || Array.isArray(value)) return invalid(); return value as Record<string, unknown>; }
function number(value: unknown, nullable = false) { if (value === null && nullable) return; if (typeof value !== "number" || !Number.isFinite(value)) invalid(); }
function count(value: unknown) { number(value); if (!Number.isSafeInteger(value) || (value as number) < 0) invalid(); }
function month(value: unknown, nullable = false) { if (value === null && nullable) return; if (typeof value !== "string" || !/^[1-9]\d{3}-(0[1-9]|1[0-2])$/.test(value)) invalid(); }
function base(value: unknown) { const data = object(value); if (data.unit !== "TWh") invalid(); return data; }
function records(data: Record<string, unknown>) { if (!Array.isArray(data.records)) return invalid(); return data.records.map(object); }
function method(data: Record<string, unknown>) { if (typeof data.method !== "string") invalid(); }

export function parseSummary(value: unknown): SummaryResult {
  const data = base(value); count(data.count); month(data.start_month, true); month(data.end_month, true);
  for (const key of ["mean", "median", "min", "max"]) number(data[key], true);
  return data as unknown as SummaryResult;
}
export function parseTrend(value: unknown): TrendResult {
  const data = base(value); method(data); count(data.window_months);
  const seen = new Set<string>();
  for (const row of records(data)) { month(row.month); number(row.value); number(row.trend, true); if (seen.has(row.month as string)) invalid(); seen.add(row.month as string); }
  return data as unknown as TrendResult;
}
export function parseSeasonality(value: unknown): SeasonalityResult {
  const data = base(value); method(data); const seen = new Set<number>();
  for (const row of records(data)) {
    count(row.month_number); count(row.count);
    if ((row.month_number as number) < 1 || (row.month_number as number) > 12 || seen.has(row.month_number as number)) invalid();
    seen.add(row.month_number as number);
    for (const key of ["mean", "median", "min", "max"]) number(row[key], true);
  }
  if (seen.size !== 12) invalid();
  return data as unknown as SeasonalityResult;
}
export function parseCorrelation(value: unknown): CorrelationResult {
  const data = base(value); if (data.method !== "pearson" || !Array.isArray(data.features) || data.features.length !== 3 || new Set(data.features).size !== 3 || data.features.some(f => !CORRELATION_FEATURES.includes(f))) invalid();
  const matrix = object(data.matrix), counts = object(data.pair_counts);
  for (const a of CORRELATION_FEATURES) for (const b of CORRELATION_FEATURES) {
    const r = object(matrix[a])[b]; number(r, true); if (typeof r === "number" && Math.abs(r) > 1.000001) invalid();
    count(object(counts[a])[b]);
  }
  return data as unknown as CorrelationResult;
}
export function parseDistribution(value: unknown): DistributionResult {
  const data = base(value); count(data.count); if (!Array.isArray(data.bins)) return invalid();
  let sum = 0;
  for (const item of data.bins) { const bin = object(item); number(bin.start); number(bin.end); count(bin.count); if ((bin.start as number) > (bin.end as number)) invalid(); sum += bin.count as number; }
  if (sum !== data.count) invalid();
  return data as unknown as DistributionResult;
}
export function parseDashboard(value: unknown): DashboardResult {
  const data = base(value);
  for (const key of ["record_count", "dataset_count", "model_run_count"]) count(data[key]);
  for (const key of ["mean_demand_twh", "minimum_demand_twh", "maximum_demand_twh", "latest_demand_twh", "change_from_previous_month_pct"]) number(data[key], true);
  month(data.start_month, true); month(data.latest_month, true);
  if (data.data_updated_at !== null && (typeof data.data_updated_at !== "string" || !Number.isFinite(Date.parse(data.data_updated_at)))) invalid();
  return data as unknown as DashboardResult;
}

export function analyticsPath(endpoint: AnalyticsEndpoint, params: AnalyticsParams = {}) {
  const query = new URLSearchParams(Object.entries(params).sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => [key, String(value)]));
  return endpoint + (query.size ? `?${query}` : "");
}
export async function fetchAnalytics<T>(endpoint: AnalyticsEndpoint, params: AnalyticsParams, parse: (value: unknown) => T, { signal, baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001", timeoutMs = 15000 }: { signal?: AbortSignal; baseUrl?: string; timeoutMs?: number } = {}): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const response = await fetch(resolveApiBase(baseUrl) + analyticsPath(endpoint, params), { credentials: "include", cache: "no-store", headers: { Accept: "application/json" }, signal: controller.signal });
    if (!response.ok) throw new DemandApiError(response.status, response.status === 503 ? "Dịch vụ phân tích hoặc cơ sở dữ liệu chưa sẵn sàng. Vui lòng thử lại." : response.status === 403 ? "Tài khoản không có quyền xem kết quả này." : `Không tải được kết quả phân tích (HTTP ${response.status}).`);
    return parse(await response.json());
  } catch (error) {
    if (signal?.aborted) throw error;
    if (timedOut) throw new Error("API phân tích phản hồi quá lâu. Vui lòng thử lại.");
    if (error instanceof TypeError) throw new Error("Không kết nối được API phân tích. Hãy kiểm tra backend.");
    if (error instanceof SyntaxError) throw new Error("API phân tích không trả về JSON hợp lệ.");
    throw error;
  } finally { clearTimeout(timer); signal?.removeEventListener("abort", abort); }
}
