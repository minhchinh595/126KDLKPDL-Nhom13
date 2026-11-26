import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";
import ts from "typescript";
const source = await readFile(new URL("./demand-api.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { parseDemandDataset, fetchDemandDataset, DemandApiError, resolveApiBase, loginForDemand, brisbaneDate } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
const row = (id, day, value) => ({ id, dataset_name: "Open Electricity NEM", network_code: "NEM", metric: "demand", interval: "1d", unit: "MW", observed_at: `${day}T00:00:00+10:00`, value, result: "actual", grouping_type: "network", grouping_code: "", timezone: "Australia/Brisbane" });
const fixture = (records = [row(1, "2025-01-01", 100), row(2, "2025-01-02", 120)], page = 1, total = records.length) => ({ dataset_name: "Open Electricity NEM", network_code: "NEM", metric: "demand", interval: "1d", unit: "MW", timezone: "Australia/Brisbane", page, page_size: 1000, total_matches: total, coverage: { returned_count: records.length }, records });

test("NEM adapter validates actual observation fields and Brisbane date order", () => {
  const data = parseDemandDataset(fixture([row(2, "2025-01-02", 120), row(1, "2025-01-01", 0)]));
  assert.equal(data.records[0].value, 0); assert.equal(data.records[0].observed_at, "2025-01-01T00:00:00+10:00");
  assert.equal(data.start_date, "2025-01-01"); assert.equal(data.end_date, "2025-01-02"); assert.equal(data.unit, "MW");
});
test("NEM parser rejects wrong identity, malformed timestamps, values and duplicate natural keys", () => {
  for (const alter of [data => { data.dataset_name = "VNM"; }, data => { data.network_code = "NSW1"; }, data => { data.records[0].unit = "TWh"; }, data => { data.records[0].interval = "5m"; }, data => { data.records[0].observed_at = "2025-01-01T00:00:00"; }, data => { data.records[0].value = NaN; }, data => { data.records[0].value = -1; }, data => { data.records[0].grouping_type = "region"; }, data => { data.records[1] = { ...data.records[0], id: 3 }; }]) { const data = fixture(); alter(data); assert.throws(() => parseDemandDataset(data)); }
});
test("distinct NEM result records may share a Brisbane date", () => {
  const first = row(1, "2025-01-01", 100), second = { ...row(2, "2025-01-01", 90), result: "forecast" };
  assert.equal(parseDemandDataset(fixture([first, second])).records.length, 2);
});
test("empty NEM result is represented without fabricating records", () => { const data = parseDemandDataset(fixture([], 1, 0)); assert.deepEqual(data.records, []); assert.equal(data.start_date, null); });
test("Brisbane date conversion preserves network-local calendar date", () => { assert.equal(brisbaneDate("2025-01-01T14:30:00Z"), "2025-01-02"); });
test("fetch requests daily demand pages from Gateway with cookies", async t => {
  t.mock.method(globalThis, "fetch", async (url, options) => { assert.equal(url, "http://test.local/api/electricity/demand?interval=1d&page=1&page_size=1000"); assert.equal(options.credentials, "include"); assert.equal(options.cache, "no-store"); assert.equal(options.headers.Accept, "application/json"); return Response.json(fixture()); });
  const result = await fetchDemandDataset({ baseUrl: "http://test.local/" }); assert.equal(result.total_matches, 2);
});
test("pagination fetches every NEM observation and rejects duplicate rows between pages", async t => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async (_, options) => { calls++; assert.equal(options.credentials, "include"); return Response.json(calls === 1 ? fixture([row(1, "2025-01-01", 100), row(2, "2025-01-02", 120)], 1, 3) : fixture([row(3, "2025-01-03", 130)], 2, 3)); });
  const data = await fetchDemandDataset(); assert.equal(calls, 2); assert.equal(data.total_matches, 3); assert.equal(data.end_date, "2025-01-03");
});
test("missing next-page records do not silently truncate observations", async t => { let calls = 0; t.mock.method(globalThis, "fetch", async () => { calls++; return Response.json(calls === 1 ? fixture([row(1, "2025-01-01", 100)], 1, 2) : fixture([], 2, 2)); }); await assert.rejects(fetchDemandDataset()); });
test("HTTP, invalid JSON, network failure and timeout do not use fallback data", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response("unavailable", { status: 503 })); await assert.rejects(fetchDemandDataset({ baseUrl: "http://test.local" }), /503/);
  t.mock.method(globalThis, "fetch", async () => new Response("bad json")); await assert.rejects(fetchDemandDataset(), /JSON/);
});
test("network failures and timeout are surfaced", async t => {
  t.mock.method(globalThis, "fetch", async () => { throw new TypeError("offline"); }); await assert.rejects(fetchDemandDataset(), /NEXT_PUBLIC_API_URL/);
  t.mock.method(globalThis, "fetch", (_, { signal }) => new Promise((_, reject) => signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true }))); await assert.rejects(fetchDemandDataset({ timeoutMs: 10 }), /phản hồi quá lâu/);
});
test("401 and 403 remain distinct", async t => { t.mock.method(globalThis, "fetch", async () => new Response("", { status: 401 })); await assert.rejects(fetchDemandDataset(), error => error instanceof DemandApiError && error.status === 401); t.mock.method(globalThis, "fetch", async () => new Response("", { status: 403 })); await assert.rejects(fetchDemandDataset(), error => error instanceof DemandApiError && error.status === 403); });
test("login keeps cookie authentication and exact password", async t => { t.mock.method(globalThis, "fetch", async (url, options) => { assert.equal(url, "http://test.local/api/auth/login"); assert.equal(options.credentials, "include"); assert.equal(options.method, "POST"); assert.deepEqual(JSON.parse(options.body), { email: "admin@example.com", password: " private password " }); return Response.json({}); }); await loginForDemand(" admin@example.com ", " private password ", "http://test.local"); });
test("local API keeps same-site browser hostname and blocks internal service ports", () => { assert.equal(resolveApiBase("http://127.0.0.1:8001", "localhost"), "http://localhost:8001"); for (const port of [8101, 8102, 8103, 8104, 8105, 5433, 5435]) assert.throws(() => resolveApiBase(`http://localhost:${port}`)); });
