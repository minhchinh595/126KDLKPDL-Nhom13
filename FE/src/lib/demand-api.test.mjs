import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";
import ts from "typescript";
import { existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const source = await readFile(new URL("./demand-api.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { parseDemandDataset, fetchDemandDataset } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
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

test("actual backend response matches the frontend contract", t => {
  const python = fileURLToPath(new URL("../../../BE/.venv/Scripts/python.exe", import.meta.url));
  if (!existsSync(python)) { t.skip("Backend Windows virtual environment is not installed"); return; }
  const payload = execFileSync(python, ["-c", "import os; from fastapi import Response; from app.services.electricity import DEFAULT_DATA_PATH; from app.api.routes.electricity import get_demand, DemandResponse; os.environ['ELECTRICITY_DATA_PATH'] = str(DEFAULT_DATA_PATH); print(DemandResponse.model_validate(get_demand(Response())).model_dump_json())"], { cwd: new URL("../../../BE/", import.meta.url), encoding: "utf8" });
  const response = JSON.parse(payload);
  const data = parseDemandDataset(response);
  assert.ok(data.total > 0);
  assert.deepEqual(data.records, response.records);
  assert.equal(data.start_month, data.records[0].month);
  assert.equal(data.end_month, data.records.at(-1).month);
});
test("fetch uses configured endpoint and no-store, then validates response", async t => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "http://test.local/api/electricity/demand");
    assert.equal(options.cache, "no-store");
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
