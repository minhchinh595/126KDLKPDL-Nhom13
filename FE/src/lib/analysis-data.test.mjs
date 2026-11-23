import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";
import ts from "typescript";

// Load the pure TypeScript helpers without a browser or additional test runner.
const source = await readFile(new URL("./analysis-data.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } });
const { aggregateDemand, movingAverage, seasonalPattern, pairedObservations, pearson, spearman, demandLevel, filterDemand, monthlyChanges, summarizeDemand } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

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

test("dashboard summary uses selected records and latest calendar month, not array order", () => {
  const all = [{ month: "2024-01", value: 10 }, { month: "2025-01", value: 10 }, { month: "2025-02", value: 30 }];
  const summary = summarizeDemand([all[2], all[1]], all);
  assert.equal(summary.latest.month, "2025-02");
  assert.equal(summary.total, 40); assert.equal(summary.average, 20); assert.equal(summary.count, 2);
  assert.equal(summary.peak.month, "2025-02"); assert.equal(summary.low.month, "2025-01");
  assert.equal(summary.latest.mom, 200);
  assert.equal(summary.levels.reduce((sum, level) => sum + level.count, 0), 2);
  assert.equal(summary.levels.reduce((sum, level) => sum + level.percentage, 0), 100);
});
test("dashboard preserves zero growth and does not invent missing or zero-baseline growth", () => {
  const all = [{ month: "2024-01", value: 10 }, { month: "2024-02", value: 0 }, { month: "2025-01", value: 10 }, { month: "2025-02", value: 20 }];
  const rows = monthlyChanges(all.slice(2), all);
  assert.equal(rows[0].yoy, 0); assert.equal(rows[1].yoy, null);
  assert.equal(rows[0].mom, null); assert.equal(rows[1].mom, 100);
});
test("dashboard demand thresholds include both boundaries exactly once", () => {
  assert.deepEqual([20.99, 21, 27, 27.01].map(demandLevel), ["low", "medium", "medium", "high"]);
});
test("dashboard date filter includes endpoints and handles empty or reversed ranges", () => {
  const all = [{ month: "2025-01", value: 10 }, { month: "2025-02", value: 20 }, { month: "2025-03", value: 30 }];
  assert.equal(filterDemand(all, "2025-01", "2025-02").length, 2);
  assert.equal(filterDemand(all, "2025-03", "2025-01").length, 0);
  assert.equal(filterDemand(all, "", "2025-03").length, 0);
  assert.equal(filterDemand(all, "2030-01", "2030-12").length, 0);
  const summary = summarizeDemand([], all);
  assert.equal(summary.latest, null); assert.equal(summary.average, null); assert.equal(summary.peak, null);
  assert.equal(summary.total, 0);
  assert.ok(summary.levels.every(level => level.count === 0 && level.percentage === 0));
});
