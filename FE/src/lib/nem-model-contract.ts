type JsonObject = Record<string, unknown>;
const CLASS_PROBABILITY_SUM_TOLERANCE = 2e-6;

const object = (value: unknown): JsonObject => value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
const isText = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const isFingerprint = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/i.test(value);
const validDate = (value: unknown): value is string => {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
};
const validTimestamp = (value: unknown) => typeof value === "string"
  && /(?:Z|[+-]\d{2}:\d{2})$/i.test(value)
  && Number.isFinite(Date.parse(value));
const addDays = (value: string, days: number) => {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
};

export function expectedNEMH2Dates(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Australia/Brisbane", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  const asOfDate = `${values.year}-${values.month}-${values.day}`;
  return { cutoffDate: addDays(asOfDate, -1), forecastDate: addDays(asOfDate, 1) };
}

export function nemH2RunContractError(input: unknown): string | null {
  const run = object(input), metrics = object(run.metrics), parameters = object(run.parameters);
  const provenance = object(parameters.provenance);
  if (run.status !== "completed") return "Lượt chạy H2 chưa hoàn tất.";
  if (provenance.dataset_name !== "Open Electricity NEM"
      || provenance.dataset_source !== "https://api.openelectricity.org.au/v4/market/network/NEM"
      || provenance.network_code !== "NEM" || provenance.metric !== "demand"
      || provenance.interval !== "1d" || provenance.unit !== "MW") {
    return "Provenance của lượt chạy không khớp Open Electricity NEM daily demand MW.";
  }
  if (provenance.horizon_days !== 2 || provenance.feature_schema_version !== "nem_daily_demand_h2_v1"
      || !Number.isSafeInteger(provenance.dataset_id) || Number(provenance.dataset_id) < 1) {
    return "Lượt chạy không sử dụng contract NEM H2.";
  }
  const stage = metrics.stage;
  const modelMetadata = object(provenance.model);
  const expectedArtifact = run.model_type === "prediction"
    ? "electricity_nem_daily_demand_rf_h2.joblib"
    : run.model_type === "classification"
      ? "electricity_nem_daily_demand_classifier_h2.joblib"
      : null;
  const artifact = stage === "training" ? modelMetadata.artifact_name : metrics.artifact_name;
  if (!expectedArtifact || artifact !== expectedArtifact) return "Artifact của lượt chạy không khớp model NEM H2.";
  if (stage === "training") {
    if (modelMetadata.model_type !== run.model_type || modelMetadata.horizon_days !== 2
        || modelMetadata.feature_schema_version !== "nem_daily_demand_h2_v1") {
      return "Metadata huấn luyện không khớp model NEM H2.";
    }
    return null;
  }
  if (stage !== "forecast" || metrics.forecast_status !== "ready" || metrics.horizon_days !== 2
      || metrics.network_code !== "NEM" || metrics.metric !== "demand"
      || metrics.interval !== "1d" || metrics.unit !== "MW") {
    return "Response forecast thiếu trường bắt buộc hoặc không khớp contract H2.";
  }
  if (!validDate(metrics.forecast_date) || !validDate(metrics.cutoff_date) || !validDate(metrics.last_observed_date)
      || addDays(metrics.cutoff_date, 2) !== metrics.forecast_date
      || metrics.last_observed_date !== metrics.cutoff_date || !validTimestamp(metrics.last_observed_at)) {
    return "Ngày forecast/cutoff không hợp lệ theo horizon H2.";
  }
  if (!isText(metrics.model_name) || !isFingerprint(metrics.training_data_fingerprint)
      || !isFingerprint(metrics.run_data_fingerprint)) {
    return "Response forecast thiếu model hoặc fingerprint hợp lệ.";
  }
  const datasetProvenance = object(metrics.dataset_provenance);
  if (datasetProvenance.dataset_id !== provenance.dataset_id
      || datasetProvenance.dataset_name !== provenance.dataset_name
      || datasetProvenance.dataset_source !== provenance.dataset_source) {
    return "Dataset provenance trong forecast response không khớp ModelRun.";
  }
  if (run.model_type === "prediction") {
    if (typeof metrics.predicted_demand !== "number" || !Number.isFinite(metrics.predicted_demand) || metrics.predicted_demand < 0) {
      return "Prediction result không hợp lệ.";
    }
  } else if (run.model_type === "classification") {
    const probabilities = object(metrics.probabilities);
    const low = probabilities.Low, high = probabilities.High;
    if ((metrics.predicted_level !== "Low" && metrics.predicted_level !== "High")
        || typeof metrics.threshold_mw !== "number" || !Number.isFinite(metrics.threshold_mw)
        || !isText(metrics.threshold_rule)
        || typeof low !== "number" || !Number.isFinite(low) || low < 0 || low > 1
        || typeof high !== "number" || !Number.isFinite(high) || high < 0 || high > 1) {
      return "Classification result thiếu nhãn, threshold hoặc xác suất Low/High hữu hạn trong [0,1].";
    }
    if (Math.abs(low + high - 1) > CLASS_PROBABILITY_SUM_TOLERANCE) {
      return "Tổng xác suất Low/High phải bằng 1 trong tolerance 2e-6.";
    }
  }
  return null;
}

export function nemH2FailedRunIdentityError(input: unknown): string | null {
  const run = object(input), parameters = object(run.parameters), provenance = object(parameters.provenance);
  if (run.status !== "failed") return "Lượt chạy không ở trạng thái thất bại.";
  if (run.model_type !== "prediction" && run.model_type !== "classification") return "Loại model không thuộc NEM H2.";
  if (provenance.dataset_name !== "Open Electricity NEM"
      || provenance.dataset_source !== "https://api.openelectricity.org.au/v4/market/network/NEM"
      || provenance.network_code !== "NEM" || provenance.metric !== "demand"
      || provenance.interval !== "1d" || provenance.unit !== "MW"
      || provenance.horizon_days !== 2 || provenance.feature_schema_version !== "nem_daily_demand_h2_v1"
      || !Number.isSafeInteger(provenance.dataset_id) || Number(provenance.dataset_id) < 1) {
    return "Provenance của lượt thất bại không khớp NEM H2.";
  }
  if (parameters.stage !== "training" && parameters.stage !== "forecast") {
    return "Giai đoạn của lượt thất bại không hợp lệ.";
  }
  return null;
}

export function isCompletedModelTrainingRun(input: unknown): boolean {
  const run = object(input);
  const metrics = object(run.metrics);
  const parameters = object(run.parameters);
  const stage = metrics.stage ?? parameters.stage;
  return run.status === "completed" && stage === "training";
}

export function isCurrentNEMH2Forecast(input: unknown, now = new Date()): boolean {
  const run = object(input), metrics = object(run.metrics);
  const expected = expectedNEMH2Dates(now);
  return metrics.cutoff_date === expected.cutoffDate && metrics.forecast_date === expected.forecastDate;
}
