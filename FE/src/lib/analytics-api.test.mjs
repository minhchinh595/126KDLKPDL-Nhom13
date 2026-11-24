import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import assert from "node:assert/strict";
import ts from "typescript";

const compile = text => ts.transpileModule(text, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const moduleUrl = text => `data:text/javascript;base64,${Buffer.from(text).toString("base64")}`;
const demandUrl = moduleUrl(compile(await readFile(new URL("./demand-api.ts", import.meta.url), "utf8")));
const source = compile(await readFile(new URL("./analytics-api.ts", import.meta.url), "utf8")).replace('from "./demand-api"', `from "${demandUrl}"`);
const { fetchAnalytics, analyticsPath, rangeParams, parseSummary, parseTrend, parseSeasonality, parseCorrelation, parseDistribution, parseDashboard } = await import(moduleUrl(source));

const summary = () => ({ unit: "TWh", count: 2, start_month: "2025-01", end_month: "2025-02", mean: 15, median: 15, min: 10, max: 20 });
const trend = () => ({ unit: "TWh", method: "trailing_rolling_mean", window_months: 3, records: [{ month: "2025-01", value: 10, trend: null }] });
const seasonal = () => ({ unit: "TWh", method: "group_by_calendar_month", records: Array.from({ length: 12 }, (_, i) => ({ month_number: i + 1, count: 0, mean: null, median: null, min: null, max: null })) });
const correlation = () => {
  const features = ["demand", "previous_month", "previous_year"];
  return { unit: "TWh", method: "pearson", features, matrix: Object.fromEntries(features.map(a => [a, Object.fromEntries(features.map(b => [b, a === b ? 1 : null]))])), pair_counts: Object.fromEntries(features.map(a => [a, Object.fromEntries(features.map(b => [b, a === b ? 3 : 0]))])) };
};
const distribution = () => ({ unit: "TWh", count: 2, bins: [{ start: 10, end: 20, count: 2 }] });
const overview = () => ({ unit: "TWh", record_count: 2, start_month: "2025-01", latest_month: "2025-02", mean_demand_twh: 15, minimum_demand_twh: 10, maximum_demand_twh: 20, latest_demand_twh: 20, change_from_previous_month_pct: 100, dataset_count: 1, model_run_count: 0, data_updated_at: "2025-02-01T00:00:00Z" });
const endpoints = [
  ["/api/dashboard/overview", parseDashboard, overview, {}],
  ["/api/analysis/summary", parseSummary, summary, { start_month: "2025-01", end_month: "2025-02" }],
  ["/api/analysis/trend", parseTrend, trend, { start_month: "2025-01", end_month: "2025-02", window_months: 6 }],
  ["/api/analysis/seasonality", parseSeasonality, seasonal, { start_month: "2025-01", end_month: "2025-02" }],
  ["/api/analysis/correlation", parseCorrelation, correlation, { start_month: "2025-01", end_month: "2025-02" }],
  ["/api/analysis/distribution", parseDistribution, distribution, { start_month: "2025-01", end_month: "2025-02", bins: 5 }],
];
for (const [endpoint, parse, fixture, params] of endpoints) {
  test(`${endpoint} uses cookies, correct parameters and actual returned values`, async t => {
    t.mock.method(globalThis, "fetch", async (url, options) => {
      const parsedUrl = new URL(url);
      assert.equal(parsedUrl.pathname, endpoint);
      for (const [key, value] of Object.entries(params)) assert.equal(parsedUrl.searchParams.get(key), String(value));
      assert.equal(options.credentials, "include"); assert.equal(options.cache, "no-store");
      return Response.json(fixture());
    });
    assert.deepEqual(await fetchAnalytics(endpoint, params, parse, { baseUrl: "http://test.local/" }), fixture());
  });
}
test("filters produce stable query keys and pass both date boundaries", () => {
  assert.equal(analyticsPath("/api/analysis/trend", { window_months: 3, start_month: "2025-01" }), analyticsPath("/api/analysis/trend", { start_month: "2025-01", window_months: 3 }));
  assert.deepEqual(rangeParams([{ month: "2025-01" }, { month: "2025-03" }]), { start_month: "2025-01", end_month: "2025-03" });
});
test("server values are preserved instead of recalculating statistics in the client", () => {
  const data = trend(); data.records[0].trend = 123.4567;
  assert.equal(parseTrend(data).records[0].trend, 123.4567);
  const matrix = correlation(); matrix.matrix.demand.previous_month = 0.314159;
  assert.equal(parseCorrelation(matrix).matrix.demand.previous_month, 0.314159);
});
test("parsers accept empty ranges and null statistics", () => {
  assert.equal(parseSummary({ ...summary(), count: 0, start_month: null, end_month: null, mean: null, median: null, min: null, max: null }).mean, null);
  assert.equal(parseTrend({ ...trend(), records: [] }).records.length, 0);
  assert.equal(parseSeasonality(seasonal()).records.length, 12);
  assert.equal(parseDistribution({ unit: "TWh", count: 0, bins: [] }).count, 0);
  assert.equal(parseDashboard({ ...overview(), record_count: 0, start_month: null, latest_month: null, mean_demand_twh: null, minimum_demand_twh: null, maximum_demand_twh: null, latest_demand_twh: null, change_from_previous_month_pct: null, data_updated_at: null }).latest_demand_twh, null);
});
test("parsers reject invalid units, numbers, dates, features and histogram counts", () => {
  assert.throws(() => parseSummary({ ...summary(), unit: "MW" }));
  assert.throws(() => parseSummary({ ...summary(), mean: "15" }));
  assert.throws(() => parseSummary({ ...summary(), count: -1 }));
  assert.throws(() => parseTrend({ ...trend(), records: [{ month: "2025-13", value: 10, trend: null }] }));
  assert.throws(() => parseTrend({ ...trend(), records: [{ month: "2025-01", value: Infinity, trend: null }] }));
  assert.throws(() => parseSeasonality({ ...seasonal(), records: [] }));
  assert.throws(() => parseCorrelation({ ...correlation(), features: ["demand", "previous_month", "month_number"] }));
  const matrix = correlation(); matrix.matrix.demand.demand = 2; assert.throws(() => parseCorrelation(matrix));
  assert.throws(() => parseDistribution({ ...distribution(), count: 3 }));
  assert.throws(() => parseDashboard({ ...overview(), data_updated_at: "invalid" }));
});
for (const status of [401, 403, 422, 503]) {
  test(`HTTP ${status} is surfaced without a local data fallback`, async t => {
    t.mock.method(globalThis, "fetch", async () => new Response("error", { status }));
    await assert.rejects(fetchAnalytics("/api/analysis/summary", {}, parseSummary), error => error.status === status);
  });
}
test("malformed JSON and invalid successful responses are rejected", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response("not JSON"));
  await assert.rejects(fetchAnalytics("/api/analysis/summary", {}, parseSummary), /JSON/);
});
test("cancelled filter requests cannot return obsolete results", async t => {
  t.mock.method(globalThis, "fetch", (_, { signal }) => new Promise((_, reject) => { signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true }); }));
  const controller = new AbortController();
  const request = fetchAnalytics("/api/analysis/trend", { window_months: 3 }, parseTrend, { signal: controller.signal });
  controller.abort(); await assert.rejects(request, { name: "AbortError" });
});
test("analysis timeout is reported", async t => {
  t.mock.method(globalThis, "fetch", (_, { signal }) => new Promise((_, reject) => { signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true }); }));
  await assert.rejects(fetchAnalytics("/api/analysis/summary", {}, parseSummary, { timeoutMs: 10 }), /phản hồi quá lâu/);
});
test("parsers consume real Analysis Service output for the project CSV and empty ranges", t => {
  const python = fileURLToPath(new URL("../../../BE/.venv/Scripts/python.exe", import.meta.url));
  if (!existsSync(python)) { t.skip("Backend Windows virtual environment is not installed"); return; }
  const script = `
import json
from app.services.electricity import load_demand
from service_apps.analysis.main import summary, trend, seasonality, correlation, distribution
from service_apps.analysis.schemas import AnalysisRecordsRequest, TrendRequest, DistributionRequest
from app.schemas.dashboard import DashboardOverview
rows = load_demand()['records']
def run(records):
    request = AnalysisRecordsRequest(records=records)
    return {'summary':summary(request), 'trend':trend(TrendRequest(records=records,window_months=6)), 'seasonality':seasonality(request), 'correlation':correlation(request), 'distribution':distribution(DistributionRequest(records=records,bins=10))}
print(json.dumps({'real':run(rows), 'empty':run([])}))
`;
  const result = JSON.parse(execFileSync(python, ["-c", script], { cwd: new URL("../../../BE/", import.meta.url), encoding: "utf8" }));
  for (const [kind, data] of Object.entries(result)) {
    const summaryData = parseSummary(data.summary);
    assert.equal(parseTrend(data.trend).records.length, summaryData.count);
    assert.equal(parseSeasonality(data.seasonality).records.reduce((sum, row) => sum + row.count, 0), summaryData.count);
    assert.equal(parseDistribution(data.distribution).count, summaryData.count);
    assert.equal(parseCorrelation(data.correlation).features.length, 3);
    assert.equal(kind === "empty" ? summaryData.count === 0 : summaryData.count > 0, true);
  }
});
