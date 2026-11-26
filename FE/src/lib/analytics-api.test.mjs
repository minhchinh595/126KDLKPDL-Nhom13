import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";
import ts from "typescript";

const compile = source => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const moduleUrl = source => `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
const demandUrl = moduleUrl(compile(await readFile(new URL("./demand-api.ts", import.meta.url), "utf8")));
const source = compile(await readFile(new URL("./analytics-api.ts", import.meta.url), "utf8")).replace('from "./demand-api"', `from "${demandUrl}"`);
const api = await import(moduleUrl(source));

const summary = () => ({ metric: "demand", interval: "1d", unit: "MW", sample_count: 2, start_date: "2025-01-01", end_date: "2025-01-02", mean: 150, median: 150, minimum: 100, maximum: 200 });
const demandStatistics = () => ({ metric: "demand", interval: "1d", unit: "MW", count: 2, mean: 150, minimum: 100, maximum: 200, coverage: { returned_count: 2 } });
const trend = () => ({ metric: "demand", unit: "MW", view: "week", aggregation: "mean", records: [{ period: "2024-12-30", value: 150, sample_count: 2, weighted_sample_count: 2, expected_days: 7, coverage_fraction: 2 / 7 }] });
const seasonality = () => ({ metric: "demand", unit: "MW", method: "weekday_mean", limitation: "Daily coverage only", records: Array.from({ length: 7 }, (_, index) => ({ weekday: index + 1, count: index === 2 ? 2 : 0, mean: index === 2 ? 150 : null })) });
const correlation = () => {
  const metrics = { demand: { unit: "MW" }, price: { unit: "$/MWh" } };
  return { metrics, alignment: "exact_date", sample_dates: 2, matrix: { demand: { demand: 1, price: 0.5 }, price: { demand: 0.5, price: 1 } }, pair_counts: { demand: { demand: 2, price: 2 }, price: { demand: 2, price: 2 } } };
};
const distribution = () => ({ metric: "demand", interval: "1d", unit: "MW", sample_count: 2, bins: [{ start: 100, end: 150, count: 1 }, { start: 150, end: 200, count: 1 }] });
const scatter = () => ({ x: { metric: "demand", unit: "MW", interval: "1d" }, y: { metric: "price", unit: "$/MWh", interval: "1d" }, sample_count: 1, points: [{ date: "2025-01-01", x: 100, y: 50 }] });
const dashboard = () => ({ dataset_name: "Open Electricity NEM", dataset_status: "ready", total_observations: 365, latest_daily_demand_mw: 200, average_daily_demand_mw: 150, minimum_daily_demand_mw: 100, maximum_daily_demand_mw: 200, latest_renewable_proportion_percent: 34.5, latest_price_per_mwh: 50, latest_data_timestamp: "2025-01-02T00:00:00+10:00", timezone: "Australia/Brisbane" });

test("Brisbane date range uses Gateway half-open start_at/end_at parameters", () => {
  assert.deepEqual(api.rangeParams([{ date: "2025-01-01" }, { date: "2025-01-03" }]), { start_at: "2025-01-01T00:00:00+10:00", end_at: "2025-01-04T00:00:00+10:00" });
  assert.deepEqual(api.rangeParams([]), {});
  assert.equal(api.analyticsPath("/api/analysis/trend", { view: "week", start_at: "2025-01-01" }), api.analyticsPath("/api/analysis/trend", { start_at: "2025-01-01", view: "week" }));
});

test("NEM summary, trend and weekday seasonality parsers preserve API values", () => {
  assert.deepEqual(api.parseSummary(summary()), summary());
  assert.deepEqual(api.parseDemandStatistics(demandStatistics()), demandStatistics());
  assert.deepEqual(api.parseTrend(trend()), trend());
  assert.deepEqual(api.parseSeasonality(seasonality()), seasonality());
  assert.deepEqual(seasonality().records.map(row => api.seasonalityWeekdayLabel(row.weekday)), ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]);
  assert.equal(api.seasonalityWeekdayLabel(7), "Chủ Nhật");
  assert.equal(api.parseTrend(trend()).records[0].coverage_fraction, 2 / 7);
});

test("weekday seasonality presents all ISO weekdays without inventing observations", () => {
  const rows = api.seasonalityWeekdayRows([{ weekday: 7, count: 2, mean: 210 }]);
  assert.deepEqual(rows.map(row => row.weekday), [1, 2, 3, 4, 5, 6, 7]);
  assert.deepEqual(rows.slice(0, 6).map(row => [row.count, row.mean]), Array.from({ length: 6 }, () => [0, null]));
  assert.deepEqual([rows[6].count, rows[6].mean], [2, 210]);
});

test("correlation, distribution, scatter and dashboard parse actual NEM response fields", () => {
  assert.deepEqual(api.parseCorrelation(correlation()), correlation());
  assert.deepEqual(api.parseDistribution(distribution()), distribution());
  assert.deepEqual(api.parseDistribution({ ...distribution(), sample_count: 0, unit: null, bins: [] }), { ...distribution(), sample_count: 0, unit: null, bins: [] });
  assert.deepEqual(api.parseScatter(scatter()), scatter());
  assert.deepEqual(api.parseDashboard(dashboard()), dashboard());
});

test("parsers accept empty ranges and nullable statistics without inventing values", () => {
  assert.equal(api.parseSummary({ ...summary(), sample_count: 0, start_date: null, end_date: null, mean: null, median: null, minimum: null, maximum: null }).mean, null);
  assert.equal(api.parseTrend({ ...trend(), records: [] }).records.length, 0);
  assert.equal(api.parseDistribution({ ...distribution(), sample_count: 0, bins: [] }).sample_count, 0);
  assert.equal(api.parseDemandStatistics({ ...demandStatistics(), count: 0, mean: null, minimum: null, maximum: null }).mean, null);
  assert.equal(api.parseDashboard({ ...dashboard(), total_observations: 0, latest_daily_demand_mw: null, average_daily_demand_mw: null, minimum_daily_demand_mw: null, maximum_daily_demand_mw: null, latest_renewable_proportion_percent: null, latest_price_per_mwh: null, latest_data_timestamp: null }).latest_daily_demand_mw, null);
});

test("parsers reject wrong units, malformed dates, nonfinite numbers and inconsistent counts", () => {
  assert.throws(() => api.parseSummary({ ...summary(), unit: "TWh" }));
  assert.throws(() => api.parseDemandStatistics({ ...demandStatistics(), unit: "TWh" }));
  assert.throws(() => api.parseSummary({ ...summary(), mean: "150" }));
  assert.throws(() => api.parseSummary({ ...summary(), sample_count: -1 }));
  assert.throws(() => api.parseTrend({ ...trend(), records: [{ ...trend().records[0], period: "2025-13" }] }));
  assert.throws(() => api.parseTrend({ ...trend(), records: [{ ...trend().records[0], value: Infinity }] }));
  assert.throws(() => api.parseSeasonality({ ...seasonality(), records: [{ weekday: 0, count: 1, mean: 1 }] }));
  assert.throws(() => api.parseSeasonality({ ...seasonality(), records: [{ weekday: 8, count: 1, mean: 1 }] }));
  assert.throws(() => api.parseCorrelation({ ...correlation(), matrix: { ...correlation().matrix, demand: { demand: 1 } } }));
  assert.throws(() => api.parseDistribution({ ...distribution(), sample_count: 3 }));
  assert.throws(() => api.parseDistribution({ ...distribution(), unit: 123 }));
  assert.throws(() => api.parseDashboard({ ...dashboard(), dataset_name: "VNM" }));
  assert.throws(() => api.parseDashboard({ ...dashboard(), timezone: "UTC" }));
});

test("dashboard demand statistics endpoint receives interval and Brisbane date bounds", async t => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    const request = new URL(url);
    assert.equal(request.pathname, "/api/electricity/demand/statistics");
    assert.equal(request.searchParams.get("interval"), "1d");
    assert.equal(request.searchParams.get("start_at"), "2025-01-01T00:00:00+10:00");
    assert.equal(request.searchParams.get("end_at"), "2025-01-03T00:00:00+10:00");
    assert.equal(options.credentials, "include");
    return Response.json(demandStatistics());
  });
  const params = { ...api.rangeParams([{ date: "2025-01-01" }, { date: "2025-01-02" }]), interval: "1d" };
  assert.deepEqual(await api.fetchAnalytics("/api/electricity/demand/statistics", params, api.parseDemandStatistics, { baseUrl: "http://test.local" }), demandStatistics());
});

test("analysis HTTP client sends cookie-authenticated Gateway requests and exact query params", async t => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    const request = new URL(url);
    assert.equal(request.pathname, "/api/analysis/summary");
    assert.equal(request.searchParams.get("metric"), "demand");
    assert.equal(request.searchParams.get("interval"), "1d");
    assert.equal(request.searchParams.get("start_at"), "2025-01-01T00:00:00+10:00");
    assert.equal(options.credentials, "include"); assert.equal(options.cache, "no-store");
    return Response.json(summary());
  });
  assert.deepEqual(await api.fetchAnalytics("/api/analysis/summary", { metric: "demand", interval: "1d", start_at: "2025-01-01T00:00:00+10:00" }, api.parseSummary, { baseUrl: "http://test.local" }), summary());
});

for (const status of [401, 403, 422, 503]) test(`HTTP ${status} remains visible without a local fallback`, async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ detail: "Gateway error" }, { status }));
  await assert.rejects(api.fetchAnalytics("/api/analysis/summary", {}, api.parseSummary), error => error.status === status && error.detail === "Gateway error");
});

test("malformed JSON, invalid success payloads and network failures are surfaced", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response("not JSON"));
  await assert.rejects(api.fetchAnalytics("/api/analysis/summary", {}, api.parseSummary), /JSON/);
  t.mock.method(globalThis, "fetch", async () => Response.json({ ...summary(), unit: "TWh" }));
  await assert.rejects(api.fetchAnalytics("/api/analysis/summary", {}, api.parseSummary), /cấu trúc/);
  t.mock.method(globalThis, "fetch", async () => { throw new TypeError("offline"); });
  await assert.rejects(api.fetchAnalytics("/api/analysis/summary", {}, api.parseSummary), /Gateway/);
});

test("cancelled and timed out filter requests do not return obsolete results", async t => {
  t.mock.method(globalThis, "fetch", (_, { signal }) => new Promise((_, reject) => signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true })));
  const controller = new AbortController(); const pending = api.fetchAnalytics("/api/analysis/trend", {}, api.parseTrend, { signal: controller.signal }); controller.abort();
  await assert.rejects(pending, { name: "AbortError" });
  await assert.rejects(api.fetchAnalytics("/api/analysis/summary", {}, api.parseSummary, { timeoutMs: 10 }), /phản hồi quá lâu/);
});
