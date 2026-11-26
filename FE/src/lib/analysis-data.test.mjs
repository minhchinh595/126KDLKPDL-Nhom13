import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";
import ts from "typescript";

const source = await readFile(new URL("./analysis-data.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const helpers = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
const points = [
  { date: "2025-01-01", value: 100 },
  { date: "2025-01-02", value: 200 },
  { date: "2025-01-06", value: 300 },
  { date: "2025-02-01", value: 400 },
];

test("date filters are inclusive and reject empty or reversed ranges", () => {
  assert.deepEqual(helpers.filterDemand(points, "2025-01-02", "2025-01-06"), points.slice(1, 3));
  assert.deepEqual(helpers.filterDemand(points, "2025-01-06", "2025-01-02"), []);
  assert.deepEqual(helpers.filterDemand(points, "", "2025-02-01"), []);
});

test("daily demand summary reports MW statistics without treating MW as energy", () => {
  const summary = helpers.summarizeDemand(points);
  assert.equal(summary.latest.date, "2025-02-01");
  assert.equal(summary.count, 4);
  assert.equal(summary.mean, 250);
  assert.equal(summary.minimum, 100);
  assert.equal(summary.maximum, 400);
  assert.equal("total" in summary, false);
});

test("weekly buckets begin on Monday and monthly buckets preserve Brisbane calendar dates", () => {
  assert.equal(helpers.periodKey("2025-01-01", "week"), "2024-12-30");
  assert.equal(helpers.periodKey("2025-01-06", "week"), "2025-01-06");
  assert.equal(helpers.periodKey("2025-02-01", "month"), "2025-02");
  assert.equal(helpers.periodKey("2025-02-01", "day"), "2025-02-01");
});

test("aggregation returns average MW, coverage count, min and max per period", () => {
  const weekly = helpers.aggregateDemand(points.slice(0, 2), "week");
  assert.deepEqual(weekly, [{ period: "2024-12-30", sample_count: 2, mean: 150, minimum: 100, maximum: 200 }]);
});

test("empty summaries and aggregations remain empty without fabricated zero values", () => {
  assert.deepEqual(helpers.summarizeDemand([]), { latest: null, count: 0, mean: null, minimum: null, maximum: null });
  assert.deepEqual(helpers.aggregateDemand([], "day"), []);
});
