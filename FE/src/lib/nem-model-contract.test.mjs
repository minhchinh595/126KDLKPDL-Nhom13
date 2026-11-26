import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";
import ts from "typescript";

const source = await readFile(new URL("./nem-model-contract.ts", import.meta.url), "utf8");
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const api = await import(`data:text/javascript;base64,${Buffer.from(js).toString("base64")}`);

const provenance = () => ({ dataset_id: 4, dataset_name: "Open Electricity NEM", dataset_source: "https://api.openelectricity.org.au/v4/market/network/NEM", network_code: "NEM", metric: "demand", interval: "1d", unit: "MW", horizon_days: 2, feature_schema_version: "nem_daily_demand_h2_v1" });
const prediction = () => ({ model_type: "prediction", status: "completed", parameters: { provenance: provenance() }, metrics: { stage: "forecast", forecast_status: "ready", model_name: "RandomForestRegressor", network_code: "NEM", metric: "demand", interval: "1d", unit: "MW", horizon_days: 2, forecast_date: "2026-11-27", cutoff_date: "2026-11-25", last_observed_date: "2026-11-25", last_observed_at: "2026-11-25T00:00:00+10:00", predicted_demand: 18000, artifact_name: "electricity_nem_daily_demand_rf_h2.joblib", training_data_fingerprint: "a".repeat(64), run_data_fingerprint: "b".repeat(64), dataset_provenance: { dataset_id: 4, dataset_name: "Open Electricity NEM", dataset_source: "https://api.openelectricity.org.au/v4/market/network/NEM" } } });
const classification = () => ({ model_type: "classification", status: "completed", parameters: { provenance: provenance() }, metrics: { ...prediction().metrics, model_name: "RandomForestClassifier", predicted_demand: undefined, predicted_level: "High", probabilities: { Low: 0.2, High: 0.8 }, threshold_mw: 17000, threshold_rule: "Low if demand <= training median; High otherwise", artifact_name: "electricity_nem_daily_demand_classifier_h2.joblib" } });

test("Brisbane H2 dates use local calendar date across UTC boundary", () => {
  assert.deepEqual(api.expectedNEMH2Dates(new Date("2026-11-25T14:30:00.000Z")), { cutoffDate: "2026-11-25", forecastDate: "2026-11-27" });
});

test("H2 Prediction and Classification responses satisfy the display contract", () => {
  assert.equal(api.nemH2RunContractError(prediction()), null);
  assert.equal(api.nemH2RunContractError(classification()), null);
  assert.equal(api.isCurrentNEMH2Forecast(prediction(), new Date("2026-11-25T14:30:00.000Z")), true);
});

test("classification accepts Low/High probabilities summing to one", () => {
  for (const probabilities of [
    { Low: 0.8893, High: 0.1107 },
    { Low: 1, High: 0 },
    { Low: 0, High: 1 },
  ]) {
    const run = classification();
    run.metrics.probabilities = probabilities;
    assert.equal(api.nemH2RunContractError(run), null);
  }
});

test("classification rejects probabilities whose sum is outside tolerance", () => {
  for (const probabilities of [{ Low: 0.8, High: 0.3 }, { Low: 0.8, High: 0.1 }]) {
    const run = classification();
    run.metrics.probabilities = probabilities;
    assert.match(api.nemH2RunContractError(run), /Tổng xác suất/);
  }
});

test("classification rejects invalid ranges, non-finite values and missing labels", () => {
  for (const probabilities of [
    { Low: -0.1, High: 1.1 },
    { Low: Number.NaN, High: 1 },
    { Low: 0.5, High: Number.POSITIVE_INFINITY },
    { Low: 0.8 },
    { High: 0.2 },
  ]) {
    const run = classification();
    run.metrics.probabilities = probabilities;
    assert.match(api.nemH2RunContractError(run), /xác suất Low\/High hữu hạn/);
  }
});

test("completed training runs are identified separately from inference results", () => {
  const training = prediction();
  training.metrics.stage = "training";
  training.metrics.forecast_status = undefined;
  assert.equal(api.isCompletedModelTrainingRun(training), true);
  assert.equal(api.isCompletedModelTrainingRun(prediction()), false);
});

test("failed H2 runs use provenance identity checks without requiring completed forecast metrics", () => {
  const failed = prediction();
  failed.status = "failed";
  failed.parameters.stage = "forecast";
  failed.metrics = null;
  failed.error_message = "Artifact unavailable";
  assert.equal(api.nemH2FailedRunIdentityError(failed), null);
  assert.ok(api.nemH2RunContractError(failed));

  const wrongDataset = { ...failed, parameters: { stage: "forecast", provenance: { ...provenance(), dataset_name: "Legacy VNM" } } };
  assert.match(api.nemH2FailedRunIdentityError(wrongDataset), /Provenance/);
  const missingId = { ...failed, parameters: { stage: "forecast", provenance: { ...provenance(), dataset_id: null } } };
  assert.match(api.nemH2FailedRunIdentityError(missingId), /Provenance/);
  const invalidStage = { ...failed, parameters: { ...failed.parameters, stage: "unknown" } };
  assert.ok(api.nemH2FailedRunIdentityError(invalidStage));
});

test("legacy, stale and incomplete model responses are not presented as current H2 forecasts", () => {
  const legacy = prediction(); legacy.parameters.provenance.horizon_days = 1;
  assert.match(api.nemH2RunContractError(legacy), /contract NEM H2/);
  const stale = prediction(); stale.metrics.forecast_date = "2026-11-25"; stale.metrics.cutoff_date = "2026-11-23"; stale.metrics.last_observed_date = "2026-11-23";
  assert.equal(api.nemH2RunContractError(stale), null);
  assert.equal(api.isCurrentNEMH2Forecast(stale, new Date("2026-11-25T14:30:00.000Z")), false);
  const missing = prediction(); delete missing.metrics.run_data_fingerprint;
  assert.match(api.nemH2RunContractError(missing), /fingerprint/);
  const badClass = classification(); badClass.metrics.probabilities.Low = Number.NaN;
  assert.match(api.nemH2RunContractError(badClass), /xác suất/);
  const wrongArtifact = prediction(); wrongArtifact.metrics.artifact_name = "electricity_nem_daily_demand_rf.joblib";
  assert.match(api.nemH2RunContractError(wrongArtifact), /Artifact/);
});
