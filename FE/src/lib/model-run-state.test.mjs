import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";
import ts from "typescript";

const source = await readFile(new URL("./model-run-state.ts", import.meta.url), "utf8");
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const api = await import("data:text/javascript;base64," + Buffer.from(js).toString("base64"));

test("running attempt hides prior output and starts no result query", () => {
  for (const kind of ["prediction", "classification", "clustering"]) {
    assert.equal(api.modelRunQueryPath(kind, { status: "running", action: "run" }), null);
  }
});

test("success follows the exact ModelRun ID returned by the action", () => {
  const state = { status: "succeeded", action: "run", runId: 42 };
  assert.equal(api.modelRunQueryPath("prediction", state), "/api/prediction/runs/42");
  assert.equal(api.modelRunDetailMatchesId({ id: 42 }, 42), true);
  assert.equal(api.modelRunDetailMatchesId({ id: 41 }, 42), false);
});

test("a failure after success hides the earlier result and never falls back", () => {
  const previousSuccess = { status: "succeeded", action: "run", runId: 42 };
  assert.equal(api.modelRunQueryPath("prediction", previousSuccess), "/api/prediction/runs/42");
  const state = { status: "failed", action: "run", message: "service unavailable" };
  for (const kind of ["prediction", "classification", "clustering"]) {
    assert.equal(api.modelRunQueryPath(kind, state), null);
  }
});

test("not_ready keeps its dedicated no-result state", () => {
  assert.equal(api.modelRunQueryPath("prediction", { status: "not_ready", message: "missing cutoff" }), null);
});

test("history selection remains available and latest reload is explicit", () => {
  assert.equal(api.modelRunQueryPath("classification", { status: "idle", selectedRunId: 17 }), "/api/classification/runs/17");
  assert.equal(api.modelRunQueryPath("clustering", api.initialModelRunViewState), "/api/clustering/latest");
});

test("retry attempt changes the gateway query key", () => {
  const beforeRetry = api.modelRunQueryKey("/api/prediction/runs/42", 3, 0);
  const retry = api.modelRunQueryKey("/api/prediction/runs/42", 3, 1);
  assert.notEqual(retry, beforeRetry);
});
