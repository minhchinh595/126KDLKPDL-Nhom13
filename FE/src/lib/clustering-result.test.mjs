import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";
import ts from "typescript";

const source = await readFile(new URL("./clustering-result.ts", import.meta.url), "utf8");
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const api = await import(`data:text/javascript;base64,${Buffer.from(js).toString("base64")}`);

const featureNames = ["demand", "generation_renewable", "price", "renewable_proportion"];
const featureUnits = { demand: "MW", generation_renewable: "MW", price: "$/MWh", renewable_proportion: "%" };
const run = () => ({
  id: 99, model_type: "clustering", status: "completed", created_at: "2026-11-26T08:00:00Z",
  completed_at: "2026-11-26T08:00:02Z", error_message: null,
  parameters: { stage: "run", provenance: {
    dataset_id: 4, dataset_name: "Open Electricity NEM",
    dataset_source: "https://api.openelectricity.org.au/v4/market/network/NEM",
    network_code: "NEM", interval: "1d",
  } },
  metrics: {
    stage: "run", method: "KMeans", feature_set: "B", feature_names: featureNames,
    feature_units: featureUnits, scaler: "standard", selected_k: 2, run_observation_count: 4,
    silhouette_score: 0.39, run_start: "2026-11-21", run_end: "2026-11-24",
    artifact_name: "electricity_nem_daily_kmeans.joblib",
    training_data_fingerprint: "a".repeat(64), run_data_fingerprint: "b".repeat(64),
    cluster_label_semantics: "Groups of days with similar network-level operating characteristics; not geographic regions.",
    cluster_summaries: [
      { cluster_id: 0, label: "Cluster 1", day_count: 3, feature_means: { demand: 16000, generation_renewable: 4000, price: 80, renewable_proportion: 25 } },
      { cluster_id: 1, label: "Cluster 2", day_count: 1, feature_means: { demand: 19000, generation_renewable: 6000, price: 120, renewable_proportion: 31 } },
    ],
    assignments: [
      { date: "2026-11-21", cluster_id: 0, cluster_label: "Cluster 1", features: { demand: 16000, generation_renewable: 4000, price: 80, renewable_proportion: 25 } },
      { date: "2026-11-22", cluster_id: 0, cluster_label: "Cluster 1", features: { demand: 16100, generation_renewable: 4100, price: 81, renewable_proportion: 25.1 } },
      { date: "2026-11-23", cluster_id: 0, cluster_label: "Cluster 1", features: { demand: 15900, generation_renewable: 3900, price: 79, renewable_proportion: 24.9 } },
      { date: "2026-11-24", cluster_id: 1, cluster_label: "Cluster 2", features: { demand: 19000, generation_renewable: 6000, price: 120, renewable_proportion: 31 } },
    ],
    centroids_original_units: [
      { demand: 16000, generation_renewable: 4000, price: 80, renewable_proportion: 25 },
      { demand: 19000, generation_renewable: 6000, price: 120, renewable_proportion: 31 },
    ],
  },
});

test("parses completed NEM daily inference, cluster summaries, centroids and assignments", () => {
  const parsed = api.parseClusteringInference(run());
  assert.equal(parsed.state, "ready");
  assert.equal(parsed.result.datasetName, "Open Electricity NEM");
  assert.equal(parsed.result.observationCount, 4);
  assert.deepEqual(parsed.result.clusterSummaries.map(item => item.dayCount), [3, 1]);
  assert.equal(parsed.result.clusterSummaries[0].featureMeans.demand, 16000);
  assert.equal(parsed.result.assignments[3].features.renewable_proportion, 31);
  assert.equal(parsed.result.centroids.length, 2);
});

test("training run is never parsed as inference", () => {
  const training = run();
  training.metrics.stage = "training";
  training.parameters.stage = "training";
  assert.deepEqual(api.parseClusteringInference(training), { state: "training" });
});

test("failed and unfinished runs do not display clustering assignments", () => {
  const failed = run();
  failed.status = "failed";
  failed.error_message = "artifact missing";
  assert.deepEqual(api.parseClusteringInference(failed), { state: "failed", runId: 99, message: "artifact missing" });

  const running = run();
  running.status = "running";
  assert.deepEqual(api.parseClusteringInference(running), { state: "pending", runId: 99, stage: "run" });
});

test("rejects non-NEM provenance and malformed assignment rows", () => {
  const wrongDataset = run();
  wrongDataset.parameters.provenance.network_code = "NSW1";
  assert.equal(api.parseClusteringInference(wrongDataset).state, "invalid");

  const badAssignment = run();
  badAssignment.metrics.assignments[0].features.demand = Number.NaN;
  assert.equal(api.parseClusteringInference(badAssignment).state, "invalid");
});

test("rejects mismatched summary and assignment counts instead of inventing results", () => {
  const broken = run();
  broken.metrics.cluster_summaries[0].day_count = 2;
  assert.equal(api.parseClusteringInference(broken).state, "invalid");

  const missingRows = run();
  missingRows.metrics.assignments = [];
  assert.equal(api.parseClusteringInference(missingRows).state, "invalid");
});

test("maps loading, empty and API errors to distinct view states", () => {
  assert.deepEqual(api.clusteringResourceView({ status: "loading" }), { state: "loading" });
  assert.equal(api.clusteringResourceView({ status: "empty" }).state, "empty");
  assert.deepEqual(api.clusteringResourceView({ status: "error", error: new Error("Gateway 503") }), { state: "error", message: "Gateway 503" });
});

test("a completed response with no assignments is an explicit empty state", () => {
  const empty = run();
  empty.metrics.run_observation_count = 0;
  empty.metrics.cluster_summaries = [];
  empty.metrics.assignments = [];
  assert.equal(api.parseClusteringInference(empty).state, "empty");
});
