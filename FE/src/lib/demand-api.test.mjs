import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";
import ts from "typescript";
import { existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const source = await readFile(new URL("./demand-api.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { parseDemandDataset, fetchDemandDataset, DemandApiError, resolveApiBase, loginForDemand } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
const fixture = () => ({ source: "test.csv", country: "Vietnam", iso3: "VNM", unit: "TWh", total: 2, start_month: "2025-01", end_month: "2025-02", records: [{ month: "2025-02", value: 2 }, { month: "2025-01", value: 0 }] });

test("API adapter sorts months and preserves zero demand", () => {
  const data = parseDemandDataset(fixture());
  assert.equal(data.records[0].value, 0);
  assert.equal(data.records[0].month, "2025-01");
});
test("API adapter rejects wrong units, countries, dates, duplicates and mismatched metadata", () => {
  for (const alter of [data => { data.unit = "MW"; }, data => { data.iso3 = "ARG"; }, data => { data.total = 5; }, data => { data.records[0].month = "2025-13"; }, data => { data.records[0].value = NaN; }, data => { data.records[0].value = -1; }, data => { data.records[0].value = "2"; }, data => { data.records[0] = data.records[1]; }, data => { data.start_month = "2020-01"; }]) {
    const data = fixture(); alter(data); assert.throws(() => parseDemandDataset(data));
  }
});
test("API adapter accepts a successful empty result", () => {
  assert.deepEqual(parseDemandDataset({ ...fixture(), total: 0, records: [], start_month: null, end_month: null }).records, []);
});

test("current backend response schema matches the frontend contract", t => {
  const python = fileURLToPath(new URL("../../../BE/.venv/Scripts/python.exe", import.meta.url));
  if (!existsSync(python)) { t.skip("Backend Windows virtual environment is not installed"); return; }
  const payload = execFileSync(python, ["-c", "from app.api.routes.electricity import DemandResponse; print(DemandResponse(source='PostgreSQL: electricity_consumption', country='Vietnam', iso3='VNM', unit='TWh', total=1, start_month='2025-01', end_month='2025-01', page=1, page_size=1000, total_matches=1, records=[{'id':1,'month':'2025-01','value':10}]).model_dump_json())"], { cwd: new URL("../../../BE/", import.meta.url), encoding: "utf8" });
  const response = JSON.parse(payload);
  const data = parseDemandDataset(response);
  assert.ok(data.total > 0);
  assert.deepEqual(data.records, response.records.map(({ month, value }) => ({ month, value })));
  assert.equal(data.start_month, data.records[0].month);
  assert.equal(data.end_month, data.records.at(-1).month);
});
test("fetch uses configured endpoint, sends credentials and no-store, then validates response", async t => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "http://test.local/api/electricity/demand?page=1&page_size=1000");
    assert.equal(options.credentials, "include");
    assert.equal(options.cache, "no-store");
    assert.equal(options.credentials, "include");
    assert.equal(options.headers.Accept, "application/json");
    return Response.json(fixture());
  });

  assert.equal((await fetchDemandDataset({ baseUrl: "http://test.local/" })).total, 2);
});
test("HTTP errors never fall back to hardcoded data", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response("unavailable", { status: 503 }));
  await assert.rejects(fetchDemandDataset({ baseUrl: "http://test.local" }), /503/);
});
test("invalid JSON is reported", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response("<html>not JSON</html>"));
  await assert.rejects(fetchDemandDataset(), /JSON/);
});
test("network failures are reported", async t => {
  t.mock.method(globalThis, "fetch", async () => { throw new TypeError("Failed to fetch"); });
  await assert.rejects(fetchDemandDataset(), /NEXT_PUBLIC_API_URL/);
});
test("timeouts abort pending requests", async t => {
  t.mock.method(globalThis, "fetch", (_, { signal }) => new Promise((_, reject) => {
    signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
  }));
  await assert.rejects(fetchDemandDataset({ timeoutMs: 10 }), /phản hồi quá lâu/);
});
test("unmount cancellation is forwarded to fetch", async t => {
  t.mock.method(globalThis, "fetch", (_, { signal }) => new Promise((_, reject) => {
    signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
  }));
  const controller = new AbortController();
  const request = fetchDemandDataset({ signal: controller.signal });
  controller.abort();
  await assert.rejects(request, { name: "AbortError" });
});

test("local API follows browser hostname for same-site cookies; remote API is unchanged", () => {
  assert.equal(resolveApiBase("http://127.0.0.1:8000", "localhost"), "http://localhost:8000");
  assert.equal(resolveApiBase("http://localhost:8000/", "127.0.0.1"), "http://127.0.0.1:8000");
  assert.equal(resolveApiBase("https://api.example.com", "localhost"), "https://api.example.com");
  assert.equal(resolveApiBase("http://127.0.0.1:8000", "app.example.com"), "http://127.0.0.1:8000");
});
test("login sends cookie credentials and the exact password without trimming it", async t => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "http://test.local/api/auth/login");
    assert.equal(options.credentials, "include");
    assert.equal(options.method, "POST");
    assert.equal(options.cache, "no-store");
    assert.deepEqual(JSON.parse(options.body), { email: "admin@example.com", password: " private password " });
    return Response.json({ id: 1 });
  });
  await loginForDemand(" admin@example.com ", " private password ", "http://test.local");
});
test("invalid login and expired sessions expose status 401 for the login form", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response("unauthorized", { status: 401 }));
  await assert.rejects(fetchDemandDataset(), error => error instanceof DemandApiError && error.status === 401);
  await assert.rejects(loginForDemand("admin@example.com", "wrong"), error => error instanceof DemandApiError && error.status === 401);
});
test("permission denied preserves status 403 instead of showing another login", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response("forbidden", { status: 403 }));
  await assert.rejects(fetchDemandDataset(), error => error instanceof DemandApiError && error.status === 403);
});
test("all API pages are fetched with cookies so charts do not truncate history", async t => {
  const first = { ...fixture(), page: 1, page_size: 2, total_matches: 3 };
  let calls = 0;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls++;
    assert.equal(options.credentials, "include");
    assert.ok(url.includes(`page=${calls}&page_size=1000`));
    return Response.json(calls === 1 ? first : { ...fixture(), page: 2, page_size: 2, total_matches: 3, total: 1, start_month: "2025-03", end_month: "2025-03", records: [{ month: "2025-03", value: 3 }] });
  });
  const data = await fetchDemandDataset();
  assert.equal(calls, 2); assert.equal(data.total, 3); assert.equal(data.end_month, "2025-03");
});
test("missing pagination records cannot silently truncate charts", async t => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    calls++;
    return Response.json(calls === 1 ? { ...fixture(), page: 1, total_matches: 3 } : { ...fixture(), page: 2, total_matches: 3, total: 0, start_month: null, end_month: null, records: [] });
  });
  await assert.rejects(fetchDemandDataset());
});

test("duplicate months across API pages are rejected", async t => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    calls++;
    return Response.json(calls === 1 ? { ...fixture(), page: 1, total_matches: 3 } : { ...fixture(), page: 2, total_matches: 3, total: 1, start_month: "2025-01", end_month: "2025-01", records: [{ month: "2025-01", value: 0 }] });
  });
  await assert.rejects(fetchDemandDataset());
});
