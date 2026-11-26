import { readFile } from "node:fs/promises";
import test from "node:test";
import assert from "node:assert/strict";
import ts from "typescript";
const compile = text => ts.transpileModule(text, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const url = text => `data:text/javascript;base64,${Buffer.from(text).toString("base64")}`;
const dependency = url(compile(await readFile(new URL("./demand-api.ts", import.meta.url), "utf8")));
const source = compile(await readFile(new URL("./gateway.ts", import.meta.url), "utf8")).replace('from "./demand-api"', `from "${dependency}"`);
const { gatewayRequest, gatewayBase, parseUser, canManage, query, modelRunsPath, modelActionPath } = await import(url(source));

test("model history uses Gateway filter aliases and server pagination", () => {
  const path = modelRunsPath({ modelType: "prediction", status: "failed", order: "asc", page: 3, pageSize: 50 });
  const endpoint = new URL(path, "http://localhost:8001");
  assert.equal(endpoint.pathname, "/api/model-runs");
  assert.deepEqual(Object.fromEntries(endpoint.searchParams), { model_type: "prediction", status: "failed", order: "asc", page: "3", page_size: "50" });
  assert.equal(new URL(modelRunsPath(), endpoint.origin).searchParams.has("model_type"), false);
});
test("model history refuses invalid backend filters", () => {
  for (const filter of [{ modelType: "unknown" }, { status: "done" }, { order: "oldest" }, { page: 0 }, { page: 1.5 }, { pageSize: 101 }, { pageSize: 0 }]) assert.throws(() => modelRunsPath(filter));
});
for (const kind of ["clustering", "prediction", "classification"]) for (const action of ["train", "run"]) {
  test(`${kind} ${action} uses the contracted endpoint and only clustering training has max_k`, async t => {
    const path = modelActionPath(kind, action, 5);
    assert.equal(path, `/api/${kind}/${action}` + (kind === "clustering" && action === "train" ? "?max_k=5" : ""));
    t.mock.method(globalThis, "fetch", async (target, options) => {
      assert.equal(target, "http://test.local" + path);
      assert.equal(options.method, "POST"); assert.equal(options.credentials, "include"); assert.equal(options.body, undefined);
      return Response.json({ id: 7, model_type: kind });
    });
    assert.equal((await gatewayRequest(path, { baseUrl: "http://test.local", method: "POST" })).model_type, kind);
  });
}
test("clustering validates integer K range and unsupported actions", () => {
  for (const maxK of [1, 6, 2.5, NaN]) assert.throws(() => modelActionPath("clustering", "train", maxK));
  assert.equal(modelActionPath("clustering", "train", 2), "/api/clustering/train?max_k=2");
  assert.equal(modelActionPath("clustering", "train", 5), "/api/clustering/train?max_k=5");
  assert.throws(() => modelActionPath("other", "run")); assert.throws(() => modelActionPath("prediction", "delete"));
});
const user = () => ({ id: 1, username: "analyst", email: "analyst@example.com", role: "analyst", is_active: true });

test("default Gateway is port 8001", () => { const original = process.env.NEXT_PUBLIC_API_URL; delete process.env.NEXT_PUBLIC_API_URL; try { assert.equal(gatewayBase(), "http://localhost:8001"); } finally { if (original !== undefined) process.env.NEXT_PUBLIC_API_URL = original; } });
test("session parser accepts both roles and only Admin can mutate", () => { assert.equal(parseUser(user()).role, "analyst"); assert.equal(parseUser({ ...user(), role: "admin" }).role, "admin"); assert.equal(canManage("admin"), true); assert.equal(canManage("analyst"), false); });
test("invalid and inactive accounts cannot become a session", () => { for (const data of [null, {}, { ...user(), role: "owner" }, { ...user(), is_active: false }, { ...user(), id: "1" }]) assert.throws(() => parseUser(data)); });
test("JSON actions go to Gateway with cookies and no-store", async t => { t.mock.method(globalThis, "fetch", async (target, options) => { assert.equal(target, "http://test.local/api/users"); assert.equal(options.credentials, "include"); assert.equal(options.method, "POST"); assert.equal(options.cache, "no-store"); assert.equal(options.headers["Content-Type"], "application/json"); assert.equal(JSON.parse(options.body).role, "analyst"); return Response.json(user()); }); assert.equal((await gatewayRequest("/api/users", { baseUrl: "http://test.local", method: "POST", body: user() })).role, "analyst"); });
test("disabled legacy dataset upload preserves multipart encoding and surfaces HTTP 410", async t => { const body = new FormData(); body.set("name", "candidate"); body.set("file", new Blob(["network,metric,interval,observed_at,value\nNEM,demand,1d,2025-01-01T00:00:00+10:00,100"], { type: "text/csv" }), "candidate.csv"); t.mock.method(globalThis, "fetch", async (_, options) => { assert.equal(options.body, body); assert.equal(options.headers["Content-Type"], undefined); assert.equal(options.credentials, "include"); assert.equal(await options.body.get("file").text(), "network,metric,interval,observed_at,value\nNEM,demand,1d,2025-01-01T00:00:00+10:00,100"); return Response.json({ detail: "CSV dataset ingestion disabled" }, { status: 410 }); }); await assert.rejects(gatewayRequest("/api/datasets/upload", { method: "POST", body }), error => error.status === 410); });
test("logout accepts empty HTTP 204", async t => { t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 204 })); assert.equal(await gatewayRequest("/api/auth/logout", { method: "POST" }), undefined); });
for (const status of [401, 403, 409, 410, 413, 422, 503]) test(`HTTP ${status} remains actionable and is not replaced by sample data`, async t => { t.mock.method(globalThis, "fetch", async () => Response.json({ detail: "Contract error" }, { status })); await assert.rejects(gatewayRequest("/api/prediction/run", { method: "POST" }), error => error.status === status); });
test("validation details are displayed", async t => { t.mock.method(globalThis, "fetch", async () => Response.json({ detail: [{ loc: ["body", "email"], msg: "Invalid email" }] }, { status: 422 })); await assert.rejects(gatewayRequest("/api/users", { method: "POST", body: {} }), /body.email: Invalid email/); });
test("network failures never retry a write automatically", async t => { let calls = 0; t.mock.method(globalThis, "fetch", async () => { calls++; throw new TypeError("Failed to fetch"); }); await assert.rejects(gatewayRequest("/api/prediction/run", { method: "POST" })); assert.equal(calls, 1); });
test("cancellation is forwarded", async t => { t.mock.method(globalThis, "fetch", (_, { signal }) => new Promise((_, reject) => signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true }))); const controller = new AbortController(); const result = gatewayRequest("/api/model-runs", { signal: controller.signal }); controller.abort(); await assert.rejects(result, { name: "AbortError" }); });
test("internal or external service URLs are refused", async () => { await assert.rejects(gatewayRequest("http://localhost:8101/health")); await assert.rejects(gatewayRequest("/api/../internal/run")); });
test("browser client cannot use a microservice or PostgreSQL port as the Gateway", async () => { for (const port of [8101, 8102, 8103, 8104, 8105, 5433, 5435]) await assert.rejects(gatewayRequest("/api/health", { baseUrl: `http://localhost:${port}` })); });
test("queries encode search and pagination", () => { const params = new URLSearchParams(query({ search: "a&b", page: 2, role: "analyst", empty: "" }).slice(1)); assert.equal(params.get("search"), "a&b"); assert.equal(params.get("page"), "2"); assert.equal(params.has("empty"), false); });
