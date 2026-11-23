import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";
import ts from "typescript";

// Load the pure TypeScript helpers without a browser or additional test runner.
const source = await readFile(new URL("./analysis-data.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } });
const { aggregateDemand, movingAverage, seasonalPattern, pairedObservations, pearson, spearman } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

test("partial year compares only corresponding months, not a complete prior year", () => {
  const all = [{ month: "2024-01", value: 10 }, { month: "2024-02", value: 20 }, { month: "2024-03", value: 80 }, { month: "2025-01", value: 15 }, { month: "2025-02", value: 30 }];
  const [group] = aggregateDemand(all.slice(3), all, "year");
  assert.equal(group.total, 45); assert.equal(group.previous, 30); assert.equal(group.growth, 50);
});
test("missing comparison months remain null and quarter boundaries are correct", () => {
  const all = [{ month: "2025-03", value: 20 }, { month: "2025-04", value: 30 }];
  const groups = aggregateDemand(all, all, "quarter");
  assert.deepEqual(groups.map(p => p.period), ["2025-Q1", "2025-Q2"]);
  assert.equal(groups[0].previous, null); assert.equal(groups[0].growth, null);
});
test("moving average uses prior history across year boundary without future leakage", () => {
  const all = [{ month: "2024-11", value: 10 }, { month: "2024-12", value: 20 }, { month: "2025-01", value: 30 }, { month: "2025-02", value: 900 }];
  assert.equal(movingAverage([all[2]], all, 3)[0].movingAverage, 20);
  assert.equal(movingAverage([all[0]], all, 3)[0].movingAverage, null);
});
test("moving average does not cross missing months", () => {
  const all = [{ month: "2025-01", value: 10 }, { month: "2025-03", value: 30 }];
  assert.equal(movingAverage([all[1]], all, 2)[0].movingAverage, null);
});
test("seasonal averages count observations and preserve missing months", () => {
  const pattern = seasonalPattern([{ month: "2024-01", value: 10 }, { month: "2025-01", value: 20 }]);
  assert.equal(pattern[0].average, 15); assert.equal(pattern[0].count, 2);
  assert.equal(pattern[1].average, null); assert.equal(pattern[1].count, 0);
});
test("lag matching uses calendar dates, including history outside selected range", () => {
  const all = [{ month: "2024-01", value: 10 }, { month: "2024-12", value: 20 }, { month: "2025-01", value: 30 }];
  assert.deepEqual(pairedObservations([all[2]], all, "previousMonth", "demand"), [{ month: "2025-01", x: 20, y: 30 }]);
  assert.deepEqual(pairedObservations([all[2]], all, "previousYear", "demand"), [{ month: "2025-01", x: 10, y: 30 }]);
  assert.equal(pairedObservations([all[0]], all, "previousYear", "demand").length, 0);
});
test("correlation handles known positive, negative, small and constant samples", () => {
  assert.equal(pearson([1, 2, 3], [2, 4, 6]), 1);
  assert.equal(pearson([1, 2, 3], [6, 4, 2]), -1);
  assert.equal(pearson([1, 1, 1], [2, 3, 4]), null);
  assert.equal(pearson([1, 2], [2, 4]), null);
});
test("Spearman uses average ranks for ties", () => {
  assert.ok(Math.abs(spearman([1, 1, 2, 3], [1, 2, 3, 4]) - 0.9486832980505138) < 1e-12);
});
