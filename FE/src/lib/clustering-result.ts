type JsonObject = Record<string, unknown>;

export interface ClusteringSummary {
  clusterId: number;
  label: string;
  dayCount: number;
  featureMeans: Record<string, number>;
}

export interface ClusteringAssignment {
  date: string;
  clusterId: number;
  clusterLabel: string;
  features: Record<string, number>;
}

export interface ClusteringInference {
  runId: number;
  createdAt: string;
  completedAt: string | null;
  modelName: string;
  datasetId: number;
  datasetName: string;
  datasetSource: string;
  networkCode: "NEM";
  interval: "1d";
  featureSet: string;
  scaler: string;
  selectedK: number;
  observationCount: number;
  silhouetteScore: number;
  runStart: string;
  runEnd: string;
  artifactName: string;
  trainingDataFingerprint: string;
  runDataFingerprint: string;
  featureNames: string[];
  featureUnits: Record<string, string>;
  clusterSummaries: ClusteringSummary[];
  assignments: ClusteringAssignment[];
  centroids: Record<string, number>[];
  labelSemantics: string;
}

export type ClusteringResultView =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "empty"; message: string }
  | { state: "training" }
  | { state: "failed"; runId: number | null; message: string }
  | { state: "pending"; runId: number | null; stage: string }
  | { state: "invalid"; message: string }
  | { state: "ready"; result: ClusteringInference };

const object = (value: unknown): JsonObject | null =>
  value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : null;
const isText = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const isCount = (value: unknown) => Number.isSafeInteger(value) && Number(value) >= 0;
const finiteNumberMap = (value: unknown): Record<string, number> | null => {
  const input = object(value);
  if (!input || Object.values(input).some(item => typeof item !== "number" || !Number.isFinite(item))) return null;
  return input as Record<string, number>;
};
const validDate = (value: unknown): value is string => {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
};
const validFingerprint = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);

export function parseClusteringInference(input: unknown): ClusteringResultView {
  const run = object(input);
  if (!run || run.model_type !== "clustering") return { state: "invalid", message: "Response không phải lượt chạy Clustering." };
  const runId = Number.isSafeInteger(run.id) ? Number(run.id) : null;
  const metrics = object(run.metrics) ?? {};
  const parameters = object(run.parameters) ?? {};
  const stage = metrics.stage ?? parameters.stage;

  if (run.status === "completed" && stage === "training") return { state: "training" };
  if (run.status === "failed") {
    return {
      state: "failed",
      runId,
      message: isText(run.error_message) ? run.error_message : "Lượt chạy Clustering thất bại; Backend không cung cấp chi tiết.",
    };
  }
  if (run.status !== "completed") return { state: "pending", runId, stage: isText(stage) ? stage : "unknown" };
  if (stage !== "run") return { state: "invalid", message: "Lượt hoàn tất không phải inference Clustering; không hiển thị như kết quả phân cụm." };

  const provenance = object(parameters.provenance);
  if (!provenance || provenance.dataset_name !== "Open Electricity NEM"
      || provenance.dataset_source !== "https://api.openelectricity.org.au/v4/market/network/NEM"
      || provenance.network_code !== "NEM" || provenance.interval !== "1d"
      || !Number.isSafeInteger(provenance.dataset_id) || Number(provenance.dataset_id) < 1) {
    return { state: "invalid", message: "Dataset provenance không khớp Open Electricity NEM network daily." };
  }

  const featureSet = metrics.feature_set;
  const selectedK = metrics.selected_k;
  const observationCount = metrics.run_observation_count;
  const silhouetteScore = metrics.silhouette_score;
  const featureNames = metrics.feature_names;
  const featureUnits = object(metrics.feature_units);
  const rawSummaries = metrics.cluster_summaries;
  const rawAssignments = metrics.assignments;
  const rawCentroids = metrics.centroids_original_units;

  if (!isText(metrics.method) || !["A", "B"].includes(String(featureSet))
      || !Number.isSafeInteger(selectedK) || Number(selectedK) < 2
      || !isCount(observationCount) || typeof silhouetteScore !== "number" || !Number.isFinite(silhouetteScore)
      || silhouetteScore < -1 || silhouetteScore > 1
      || !Array.isArray(featureNames) || featureNames.length === 0
      || !featureNames.every(isText) || new Set(featureNames).size !== featureNames.length
      || !featureNames.includes("demand") || !featureUnits || !isText(metrics.scaler)
      || Object.keys(featureUnits).length !== featureNames.length
      || !featureNames.every(name => isText(featureUnits[name]))
      || !validDate(metrics.run_start) || !validDate(metrics.run_end)
      || metrics.run_start > metrics.run_end
      || !Array.isArray(rawSummaries)
      || !Array.isArray(rawAssignments) || !Array.isArray(rawCentroids) || rawCentroids.length !== selectedK
      || !isText(metrics.artifact_name) || !validFingerprint(metrics.training_data_fingerprint)
      || !validFingerprint(metrics.run_data_fingerprint) || !isText(metrics.cluster_label_semantics)) {
    return { state: "invalid", message: "Response inference thiếu trường hoặc có kiểu dữ liệu không hợp lệ." };
  }

  if (observationCount === 0 && rawAssignments.length === 0 && rawSummaries.length === 0) {
    return { state: "empty", message: "Lượt chạy chưa có ngày đủ điều kiện để hiển thị." };
  }
  if (rawSummaries.length !== selectedK) {
    return { state: "invalid", message: "Số cluster summary không khớp số cụm đã chọn." };
  }

  const summaries: ClusteringSummary[] = [];
  for (const raw of rawSummaries) {
    const summary = object(raw);
    const means = summary && finiteNumberMap(summary.feature_means);
    if (!summary || !Number.isSafeInteger(summary.cluster_id) || Number(summary.cluster_id) < 0
        || Number(summary.cluster_id) >= selectedK || !isText(summary.label)
        || !isCount(summary.day_count) || !means
        || Object.keys(means).length !== featureNames.length
        || !featureNames.every(name => Object.hasOwn(means, name))) {
      return { state: "invalid", message: "Cluster summary thiếu số ngày hoặc feature mean hợp lệ." };
    }
    summaries.push({ clusterId: Number(summary.cluster_id), label: summary.label, dayCount: Number(summary.day_count), featureMeans: means });
  }
  if (new Set(summaries.map(summary => summary.clusterId)).size !== selectedK
      || summaries.reduce((sum, summary) => sum + summary.dayCount, 0) !== observationCount) {
    return { state: "invalid", message: "Cluster summary không khớp số quan sát inference." };
  }

  const assignments: ClusteringAssignment[] = [];
  const assignmentCounts = new Map<number, number>();
  for (const raw of rawAssignments) {
    const assignment = object(raw);
    const features = assignment && finiteNumberMap(assignment.features);
    const clusterId = assignment?.cluster_id;
    const summary = summaries.find(item => item.clusterId === clusterId);
    if (!assignment || !validDate(assignment.date) || !Number.isSafeInteger(clusterId)
        || Number(clusterId) < 0 || Number(clusterId) >= selectedK || !summary
        || assignment.cluster_label !== summary.label || !features
        || Object.keys(features).length !== featureNames.length
        || !featureNames.every(name => Object.hasOwn(features, name))) {
      return { state: "invalid", message: "Danh sách phân cụm theo ngày không khớp feature schema hoặc cluster summary." };
    }
    assignmentCounts.set(Number(clusterId), (assignmentCounts.get(Number(clusterId)) ?? 0) + 1);
    assignments.push({ date: assignment.date, clusterId: Number(clusterId), clusterLabel: summary.label, features });
  }
  if (assignments.length !== observationCount
      || summaries.some(summary => assignmentCounts.get(summary.clusterId) !== summary.dayCount)) {
    return { state: "invalid", message: "Số assignment theo ngày không khớp cluster summary." };
  }

  const centroids: Record<string, number>[] = [];
  for (const raw of rawCentroids) {
    const centroid = finiteNumberMap(raw);
    if (!centroid || Object.keys(centroid).length !== featureNames.length
        || !featureNames.every(name => Object.hasOwn(centroid, name))) {
      return { state: "invalid", message: "Centroid không khớp feature schema." };
    }
    centroids.push(centroid);
  }

  if (!Number.isSafeInteger(run.id) || !isText(run.created_at) || !Number.isFinite(Date.parse(run.created_at))
      || (run.completed_at !== null && run.completed_at !== undefined && (!isText(run.completed_at) || !Number.isFinite(Date.parse(run.completed_at))))) {
    return { state: "invalid", message: "Run identity hoặc timestamp không hợp lệ." };
  }

  return {
    state: "ready",
    result: {
      runId: Number(run.id), createdAt: run.created_at,
      completedAt: typeof run.completed_at === "string" ? run.completed_at : null,
      modelName: String(metrics.method), datasetId: Number(provenance.dataset_id),
      datasetName: String(provenance.dataset_name), datasetSource: String(provenance.dataset_source),
      networkCode: "NEM", interval: "1d", featureSet: String(featureSet), scaler: String(metrics.scaler),
      selectedK: Number(selectedK), observationCount: Number(observationCount), silhouetteScore,
      runStart: String(metrics.run_start), runEnd: String(metrics.run_end),
      artifactName: String(metrics.artifact_name),
      trainingDataFingerprint: String(metrics.training_data_fingerprint),
      runDataFingerprint: String(metrics.run_data_fingerprint),
      featureNames: featureNames as string[], featureUnits: featureUnits as Record<string, string>,
      clusterSummaries: summaries.sort((left, right) => left.clusterId - right.clusterId),
      assignments, centroids, labelSemantics: String(metrics.cluster_label_semantics),
    },
  };
}

export function clusteringResourceView(resource: unknown): ClusteringResultView {
  const value = object(resource);
  if (!value) return { state: "invalid", message: "Resource Clustering không hợp lệ." };
  if (value.status === "loading" || value.status === "idle") return { state: "loading" };
  if (value.status === "error") {
    const error = object(value.error);
    return { state: "error", message: isText(error?.message) ? error.message : "Không tải được kết quả Clustering." };
  }
  if (value.status === "empty") return { state: "empty", message: "Chưa có kết quả inference Clustering NEM. Training run không được hiển thị như kết quả phân cụm." };
  if (value.status !== "success") return { state: "invalid", message: "Trạng thái tải kết quả Clustering không hợp lệ." };
  return parseClusteringInference(value.data);
}
