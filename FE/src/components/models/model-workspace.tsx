"use client";
import { useState } from "react";
import { Shapes, Sparkles, ChartNoAxesCombined } from "lucide-react";
import { PageHeading } from "@/components/shared/page-heading";
import { StatusBadge } from "@/components/shared/status-badge";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AppLayout } from "@/components/layout/app-layout";
import { useSession } from "@/components/auth/session-provider";
import { canManage, gatewayRequest, modelActionPath, query, type ModelKind, type ModelRun, type PageResult } from "@/lib/gateway";
import { DemandApiError } from "@/lib/demand-api";
import { clusteringResourceView, parseClusteringInference, type ClusteringInference, type ClusteringResultView } from "@/lib/clustering-result";
import Link from "next/link";
import { Panel, Stat, ChartFrame, DataTable, ExportCsv, format } from "@/components/analysis/analysis-shared";
import { QueryState, useGatewayQuery, Pagination } from "@/components/shared/gateway-resource";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { isCompletedModelTrainingRun, isCurrentNEMH2Forecast, nemH2FailedRunIdentityError, nemH2RunContractError } from "@/lib/nem-model-contract";
import { initialModelRunViewState, modelRunDetailMatchesId, modelRunQueryPath, type ModelRunViewState } from "@/lib/model-run-state";

const titles: Record<ModelKind, string> = { clustering: "Phân cụm tiêu thụ", prediction: "Dự báo nhu cầu", classification: "Phân loại tiêu thụ" };
const record = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const numeric = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : null;
const text = (value: unknown) => typeof value === "string" ? value : typeof value === "number" ? String(value) : "—";
const fingerprint = (value: unknown) => typeof value === "string" ? value : "—";

export function ForecastPreview() {
  const result = useGatewayQuery<ModelRun>("/api/prediction/latest");
  return <QueryState resource={result} empty="Chưa có dự báo H2 cho ngày mục tiêu hiện tại. Admin có thể kiểm tra readiness tại trang Dự báo.">{run => {
    const contractError = nemH2RunContractError(run);
    if (contractError) return <p role="alert" className="text-sm text-destructive">Không thể hiển thị dự báo như kết quả NEM H2 hiện tại: {contractError}</p>;
    if (!isCurrentNEMH2Forecast(run)) return <p role="status">Forecast đã lưu không thuộc cutoff/forecast date H2 hiện tại; không hiển thị như dự báo mới nhất.</p>;
    return <ModelResult run={run} requireH2 />;
  }}</QueryState>;
}
export function ModelResult({ run, requireH2 = false }: { run: ModelRun; requireH2?: boolean }) {
  const m = run.metrics ?? {};
  const stage = text(m.stage ?? run.parameters?.stage);
  if (run.model_type === "clustering") return <ClusteringRunResult run={run} />;
  if (requireH2 && (run.model_type === "prediction" || run.model_type === "classification")) {
    if (run.status === "failed") {
      const identityError = nemH2FailedRunIdentityError(run);
      if (identityError) return <p role="alert" className="text-sm text-destructive">Lượt thất bại không được hiển thị vì {identityError}</p>;
      const timestamp = run.completed_at ?? run.started_at ?? run.created_at;
      const timestampText = typeof timestamp === "string" && Number.isFinite(Date.parse(timestamp))
        ? new Date(timestamp).toLocaleString("vi-VN", { timeZone: "Australia/Brisbane" })
        : null;
      const errorMessage = typeof run.error_message === "string" && run.error_message.trim() ? run.error_message : null;
      return <div className="space-y-3 rounded-lg border border-destructive/40 p-4">
        <div className="flex flex-wrap items-center gap-3"><span>Lượt #{run.id}</span><StatusBadge status="failed" /><span>{stage === "training" ? "Huấn luyện" : "Chạy mô hình"}</span>{timestampText && <span className="text-xs text-muted-foreground">{timestampText} (Australia/Brisbane)</span>}</div>
        <p role={errorMessage ? "alert" : "status"} className={errorMessage ? "text-sm text-destructive" : "text-sm text-muted-foreground"}>
          {errorMessage ?? "Lượt chạy thất bại; Backend không cung cấp chi tiết lỗi."}
        </p>
      </div>;
    }
    if (run.status !== "completed") {
      return <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border p-4" role="status">
        <span>Lượt #{run.id}</span><StatusBadge status={text(run.status)} /><span>{stage}</span>
        <span>Lượt này chưa hoàn tất; không hiển thị như một kết quả dự báo.</span>
      </div>;
    }
    const contractError = nemH2RunContractError(run);
    if (contractError) return <p role="alert" className="text-sm text-destructive">Lượt này không đáp ứng contract NEM H2 nên kết quả không được trình bày: {contractError}</p>;
  }
  if (isCompletedModelTrainingRun(run)) {
    const trainingProvenance = record(run.parameters?.provenance ?? m.dataset_provenance);
    return <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <StatusBadge status="completed" />
        <span>Lượt huấn luyện mô hình đã hoàn tất.</span>
        <span className="text-muted-foreground">Lượt này không chứa kết quả dự báo hoặc phân loại inference.</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Stat label="Mô hình" value={text(m.model_name ?? m.method)} detail={titles[run.model_type]} />
        <Stat label="Dataset / network" value={text(trainingProvenance.dataset_name ?? m.network_code)} detail={`${text(trainingProvenance.network_code ?? m.network_code)} · ${text(trainingProvenance.interval ?? m.interval)} · ${text(trainingProvenance.unit ?? m.unit)}`} />
      </div>
      <ProvenanceDetails provenance={trainingProvenance} metrics={m} />
      <details>
        <summary className="cursor-pointer text-sm">Metrics huấn luyện/validation</summary>
        <pre className="mt-2 overflow-auto rounded bg-muted p-3 text-xs">{JSON.stringify(m, null, 2)}</pre>
      </details>
    </div>;
  }
  const provenance = record(run.parameters?.provenance ?? m.dataset_provenance);
  const contractVersion = text(provenance.feature_schema_version ?? m.feature_schema_version);
  const horizonDays = numeric(provenance.horizon_days ?? m.horizon_days);
  const forecastDate = typeof m.forecast_date === "string" ? m.forecast_date : null;
  const forecastValue = numeric(m.predicted_demand);
  const probabilityMap = record(m.probabilities);
  const probabilities = ["Low", "High"].flatMap(label => numeric(probabilityMap[label]) === null ? [] : [{ label, probability: numeric(probabilityMap[label])! }]);
  const dateTime = (value: unknown) => { if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) return "—"; return new Date(value).toLocaleString("vi-VN", { timeZone: "Australia/Brisbane" }); };
  return <div className="space-y-4">
    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground"><span>Lượt #{run.id}</span><StatusBadge status={run.status} /><span>{stage === "training" ? "Huấn luyện" : "Kết quả chạy"}</span>{(run.model_type === "prediction" || run.model_type === "classification") && <span>Contract: {contractVersion} · horizon {horizonDays ?? "—"} ngày</span>}<span>{new Date(run.created_at).toLocaleString("vi-VN")}</span></div>
    {run.error_message && <p role="alert" className="text-sm text-destructive">{run.error_message}</p>}
    {run.status !== "completed" && !run.error_message && <p role="status">Lượt này chưa có kết quả hoàn tất.</p>}
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4"><Stat label="Mô hình" value={text(m.model_name ?? m.method)} detail={titles[run.model_type]} /><Stat label="Giai đoạn" value={stage} detail={text(m.target ?? m.feature_set ?? m.feature_set_name)} /><Stat label="Dataset / network" value={text(provenance.dataset_name ?? m.network_code)} detail={`${text(provenance.network_code ?? m.network_code)} · ${text(provenance.interval ?? m.interval)} · ${text(provenance.unit ?? m.unit)}`} /></div>
    {run.model_type === "prediction" && <>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4"><Stat label="Ngày dự báo" value={forecastDate ?? "—"} detail={`Horizon ${text(m.horizon_days)} ngày`} /><Stat label="Demand dự báo" value={forecastValue === null ? "—" : `${format(forecastValue)} ${text(m.unit)}`} detail={`Cutoff ${text(m.cutoff_date)}`} /><Stat label="Quan sát cuối" value={text(m.last_observed_date)} detail={dateTime(m.last_observed_at)} /></div>
      <ProvenanceDetails provenance={provenance} metrics={m} />
    </>}
    {run.model_type === "classification" && <>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4"><Stat label="Ngày phân loại" value={forecastDate ?? "—"} detail={`Horizon ${text(m.horizon_days)} ngày · cutoff ${text(m.cutoff_date)}`} /><Stat label="Mức dự báo" value={text(m.predicted_level)} detail={`Ngưỡng ${format(numeric(m.threshold_mw))} MW`} /><Stat label="Quan sát cuối" value={text(m.last_observed_date)} detail={dateTime(m.last_observed_at)} /></div>
      {m.threshold_rule && <p className="text-sm text-muted-foreground">Quy tắc ngưỡng: {text(m.threshold_rule)}</p>}
      {probabilities.length > 0 && <><ChartFrame label="Xác suất classification Low và High"><ResponsiveContainer width="100%" height="100%"><BarChart data={probabilities}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="label" /><YAxis domain={[0, 1]} /><Tooltip formatter={value => `${format(Number(value) * 100)}%`} /><Bar dataKey="probability" name="Xác suất" fill="#10b981" /></BarChart></ResponsiveContainer></ChartFrame><DataTable caption="Xác suất Low High" headers={["Nhãn", "Xác suất"]} rows={probabilities.map(row => [row.label, `${format(row.probability * 100)}%`])} /><ExportCsv filename={`classification-run-${run.id}.csv`} headers={["Forecast date", "Label", "Probability"]} rows={probabilities.map(row => [forecastDate, row.label, row.probability])} /></>}
      <ProvenanceDetails provenance={provenance} metrics={m} />
    </>}
    {stage === "training" && <details><summary className="cursor-pointer text-sm">Training/validation metrics</summary><pre className="mt-2 overflow-auto rounded bg-muted p-3 text-xs">{JSON.stringify(m, null, 2)}</pre></details>}
  </div>;
}

type ClusteringResource = {
  status: "idle" | "loading" | "success" | "empty" | "error";
  data?: ModelRun;
  error?: Error;
  retry: () => void;
};

function ClusteringResourceResult({ resource }: { resource: ClusteringResource }) {
  return <ClusteringView view={clusteringResourceView(resource)} retry={resource.retry} />;
}

function ClusteringRunResult({ run }: { run: ModelRun }) {
  return <ClusteringView view={parseClusteringInference(run)} />;
}

function ClusteringView({ view, retry }: { view: ClusteringResultView; retry?: () => void }) {
  if (view.state === "loading") return <p role="status" className="rounded-lg bg-muted/40 p-6 text-sm text-muted-foreground">Đang tải kết quả phân cụm NEM…</p>;
  if (view.state === "error") return <div role="alert" className="space-y-3 rounded-lg border border-destructive/30 bg-destructive/5 p-5 text-sm text-destructive"><p>{view.message}</p>{retry && <Button variant="outline" onClick={retry}>Thử tải lại</Button>}</div>;
  if (view.state === "empty") return <div role="status" className="rounded-lg border border-dashed border-border p-7 text-center text-sm text-muted-foreground"><p>{view.message}</p><p className="mt-2">Training run chỉ xác nhận mô hình được huấn luyện; hãy chọn một inference run để xem ngày được phân cụm.</p></div>;
  if (view.state === "training") return <div role="status" className="rounded-lg border border-border p-5 text-sm"><StatusBadge status="completed" /><p className="mt-2 font-medium">Lượt huấn luyện đã hoàn tất.</p><p className="text-muted-foreground">Lượt này chưa chứa kết quả phân cụm theo ngày. Hãy chọn một lượt inference trong lịch sử.</p></div>;
  if (view.state === "failed") return <div role="alert" className="rounded-lg border border-destructive/30 p-5 text-sm text-destructive"><p>Lượt #{view.runId ?? "—"} thất bại.</p><p className="mt-1">{view.message}</p></div>;
  if (view.state === "pending") return <div role="status" className="rounded-lg border border-border p-5 text-sm"><p>Lượt #{view.runId ?? "—"} chưa hoàn tất ({view.stage}); không hiển thị như kết quả inference.</p></div>;
  if (view.state === "invalid") return <p role="alert" className="rounded-lg border border-destructive/30 p-5 text-sm text-destructive">Không thể hiển thị kết quả Clustering: {view.message}</p>;
  return <ClusteringInferenceResult result={view.result} />;
}

const clusterMetricLabels: Record<string, string> = {
  demand: "Demand",
  price: "Giá điện",
  generation_renewable: "Phát điện tái tạo",
  renewable_proportion: "Tỷ trọng tái tạo",
};
const clusterTableMetrics = ["demand", "price", "generation_renewable", "renewable_proportion"];
const metricValue = (features: Record<string, number>, name: string, units: Record<string, string>) =>
  Object.hasOwn(features, name) ? `${format(features[name])} ${units[name]}` : "—";
const clusterTime = (value: string) => new Date(value).toLocaleString("vi-VN", { timeZone: "Australia/Brisbane" });

function ClusteringInferenceResult({ result }: { result: ClusteringInference }) {
  const [dateOrder, setDateOrder] = useState<"asc" | "desc">("asc");
  const totalDays = result.clusterSummaries.reduce((sum, cluster) => sum + cluster.dayCount, 0);
  const countChart = result.clusterSummaries.map(cluster => ({ label: cluster.label, dayCount: cluster.dayCount }));
  const demandChart = result.clusterSummaries.map(cluster => ({ label: cluster.label, meanDemand: cluster.featureMeans.demand }));
  const summaryHeaders = ["Cụm", "Số ngày", ...result.featureNames.map(name => `${clusterMetricLabels[name] ?? name} trung bình (${result.featureUnits[name]})`)];
  const summaryRows = result.clusterSummaries.map(cluster => [
    cluster.label, String(cluster.dayCount), ...result.featureNames.map(name => metricValue(cluster.featureMeans, name, result.featureUnits)),
  ]);
  const orderedAssignments = [...result.assignments].sort((left, right) => dateOrder === "asc"
    ? left.date.localeCompare(right.date)
    : right.date.localeCompare(left.date));
  const assignmentHeaders = ["Ngày (Brisbane)", "Cụm", ...clusterTableMetrics.map(name => `${clusterMetricLabels[name]}${result.featureUnits[name] ? ` (${result.featureUnits[name]})` : ""}`)];
  const assignmentRows = orderedAssignments.map(item => [
    item.date, item.clusterLabel, ...clusterTableMetrics.map(name => metricValue(item.features, name, result.featureUnits)),
  ]);

  return <div className="space-y-5">
    <div className="flex flex-wrap items-center gap-3 text-sm"><span>Lượt #{result.runId}</span><StatusBadge status="completed" /><span>Inference · {clusterTime(result.completedAt ?? result.createdAt)} (Australia/Brisbane)</span></div>
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
      <Stat label="Mô hình / dataset" value={result.modelName} detail={`${result.datasetName} · ${result.networkCode} · ${result.interval}`} />
      <Stat label="Feature set / scaler" value={`${result.featureSet} · ${result.scaler}`} detail={`K = ${result.selectedK}`} />
      <Stat label="Số quan sát" value={format(result.observationCount, 0)} detail={`${result.runStart} – ${result.runEnd} (Brisbane)`} />
      <Stat label="Silhouette score" value={format(result.silhouetteScore, 5)} detail="Giá trị do Backend trả về" />
    </div>
    <p className="text-sm text-muted-foreground">{result.labelSemantics}</p>
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
      {result.clusterSummaries.map(cluster => {
        const percent = totalDays > 0 ? cluster.dayCount / totalDays * 100 : null;
        return <Panel key={cluster.clusterId} title={cluster.label} description={`${format(cluster.dayCount, 0)} ngày · ${percent === null ? "—" : `${format(percent, 2)}%`} số ngày được phân cụm`}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {clusterTableMetrics.map(name => <Stat key={name} label={`${clusterMetricLabels[name]} trung bình`} value={metricValue(cluster.featureMeans, name, result.featureUnits)} detail="Tính từ feature means trong response" />)}
          </div>
        </Panel>;
      })}
    </div>
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
      <Panel title="Số ngày theo cụm" description="Số lượng và tỷ lệ ngày lấy từ cluster_summaries.day_count.">
        <ChartFrame label="Biểu đồ số ngày theo từng cụm">
          <ResponsiveContainer width="100%" height="100%"><BarChart data={countChart} margin={{ top: 8, right: 12, left: 8, bottom: 4 }}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="label" /><YAxis allowDecimals={false} unit=" ngày" /><Tooltip formatter={value => [`${format(numeric(value), 0)} ngày`, "Số ngày"]} /><Bar dataKey="dayCount" name="Số ngày" fill="#2563eb" radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer>
        </ChartFrame>
      </Panel>
      <Panel title="Demand trung bình theo cụm" description={`Đơn vị: ${result.featureUnits.demand}. Giá trị lấy từ cluster_summaries.feature_means.demand.`}>
        <ChartFrame label="Biểu đồ demand trung bình theo cụm, đơn vị MW">
          <ResponsiveContainer width="100%" height="100%"><BarChart data={demandChart} margin={{ top: 8, right: 12, left: 8, bottom: 4 }}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="label" /><YAxis unit={` ${result.featureUnits.demand}`} /><Tooltip formatter={value => [`${format(numeric(value))} ${result.featureUnits.demand}`, "Demand trung bình"]} /><Bar dataKey="meanDemand" name={`Demand trung bình (${result.featureUnits.demand})`} fill="#059669" radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer>
        </ChartFrame>
      </Panel>
    </div>
    <Panel title="Giá trị trung bình theo cụm" description="Giữ nguyên đơn vị và feature set do Backend trả về.">
      <DataTable caption="Giá trị feature trung bình theo cụm" headers={summaryHeaders} rows={summaryRows} />
      <details className="rounded-lg border border-border p-3"><summary className="cursor-pointer text-sm font-medium">Centroid theo đơn vị gốc</summary><div className="mt-3"><DataTable caption="Centroid K-Means theo đơn vị gốc" headers={["Cụm", ...result.featureNames.map(name => `${clusterMetricLabels[name] ?? name} (${result.featureUnits[name]})`)]} rows={result.centroids.map((centroid, index) => [result.clusterSummaries[index]?.label ?? `Cluster ${index + 1}`, ...result.featureNames.map(name => metricValue(centroid, name, result.featureUnits))])} /></div></details>
    </Panel>
    <Panel title="Phân cụm theo ngày" description={`${result.assignments.length} assignments nhận từ Backend; bảng cuộn và sắp xếp theo ngày.`} actions={<div className="flex gap-2"><Button variant="outline" onClick={() => setDateOrder(value => value === "asc" ? "desc" : "asc")}>Ngày {dateOrder === "asc" ? "cũ → mới" : "mới → cũ"}</Button><ExportCsv filename={`clustering-run-${result.runId}.csv`} headers={assignmentHeaders} rows={assignmentRows} /></div>}>
      {assignmentRows.length > 0 ? <DataTable caption="Bảng phân cụm NEM theo ngày" headers={assignmentHeaders} rows={assignmentRows} /> : <p role="status" className="rounded-lg border border-dashed p-5 text-sm text-muted-foreground">Inference này chưa có assignments để hiển thị.</p>}
    </Panel>
    <ProvenanceDetails provenance={{ dataset_id: result.datasetId, dataset_name: result.datasetName, dataset_source: result.datasetSource, network_code: result.networkCode, interval: result.interval }} metrics={{ artifact_name: result.artifactName, training_data_fingerprint: result.trainingDataFingerprint, run_data_fingerprint: result.runDataFingerprint }} />
  </div>;
}

function ProvenanceDetails({ provenance, metrics }: { provenance: Record<string, unknown>; metrics: Record<string, unknown> }) {
  const training = fingerprint(metrics.training_data_fingerprint), current = fingerprint(metrics.run_data_fingerprint);
  const model = record(provenance.model);
  return <details className="rounded-lg border border-border p-3"><summary className="cursor-pointer text-sm font-medium">Dataset, dữ liệu và artifact provenance</summary><dl className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3 break-all text-xs"><Info label="Dataset" value={text(provenance.dataset_name)} /><Info label="Source" value={text(provenance.dataset_source)} /><Info label="Network / interval / unit" value={`${text(provenance.network_code)} · ${text(provenance.interval)} · ${text(provenance.unit)}`} /><Info label="Artifact" value={text(metrics.artifact_name ?? model.artifact_name)} /><Info label="Training fingerprint" value={training} /><Info label="Run fingerprint" value={current} /></dl></details>;
}
function Info({ label, value }: { label: string; value: string }) { return <div><dt className="text-muted-foreground">{label}</dt><dd className="mt-1 font-mono">{value}</dd></div>; }

function Workspace({ kind }: { kind: ModelKind }) {
  const { session } = useSession();
  const admin = session.status === "authenticated" && canManage(session.user.role);
  const [maxK, setMaxK] = useState(5), [page, setPage] = useState(1), [revision, setRevision] = useState(0);
  const [runView, setRunView] = useState<ModelRunViewState>(initialModelRunViewState);
  const selected = runView.status === "idle" ? runView.selectedRunId : runView.status === "succeeded" ? runView.runId : null;
  const [busy, setBusy] = useState(""), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const history = useGatewayQuery<PageResult<ModelRun>>(`/api/${kind}/runs${query({ page, page_size: 10 })}`, revision);
  const current = useGatewayQuery<ModelRun>(modelRunQueryPath(kind, runView), revision);
  async function perform(action: "train" | "run") {
    if (!admin || busy) return;
    if (kind === "clustering" && action === "train" && (!Number.isInteger(maxK) || maxK < 2 || maxK > 5)) { setError("K tối đa phải là số nguyên từ 2 đến 5 theo hợp đồng API hiện tại."); return; }
    setBusy(action); setError(""); setNotice(""); setRunView({ status: "running", action });
    try {
      const run = await gatewayRequest<ModelRun>(modelActionPath(kind, action, maxK), { method: "POST", timeoutMs: 180000 });
      setRunView({ status: "succeeded", action, runId: run.id }); setPage(1); setNotice(`Đã hoàn tất ${action === "train" ? "huấn luyện" : "chạy mô hình"}, lượt #${run.id}.`);
    } catch (error) {
      if (error instanceof DemandApiError) {
        const detail = error.detail;
        if (error.status === 409 && detail && typeof detail === "object" && (detail as Record<string, unknown>).forecast_status === "not_ready") {
          const body = detail as Record<string, unknown>;
          const message = `Chưa thể tạo dự báo: ${String(body.message ?? "Thiếu dữ liệu NEM cần thiết.")} Cutoff: ${String(body.cutoff_date ?? "—")}; forecast date: ${String(body.forecast_date ?? "—")}; quan sát cuối: ${String(body.last_observed_date ?? "—")}.`;
          setError(""); setRunView({ status: "not_ready", message });
        } else {
          const message = error.status === 409 ? `Model artifact bị thiếu, không tương thích hoặc service từ chối xung đột: ${error.message}`
            : error.status === 401 ? "Phiên đăng nhập hết hạn. Hãy đăng nhập lại trước khi thao tác."
              : error.status === 403 ? "Tài khoản không có quyền thực hiện thao tác này. Chỉ Admin được Train/Run."
                : error.status === 422 ? `Backend từ chối dữ liệu hoặc yêu cầu: ${error.message}`
                  : error.status === 503 ? `Backend/service hoặc PostgreSQL chưa sẵn sàng: ${error.message}`
                    : error.message;
          setError(message); setRunView({ status: "failed", action, message });
        }
      } else {
        const message = error instanceof Error ? error.message : "Thao tác thất bại.";
        setError(message); setRunView({ status: "failed", action, message });
      }
    }
    finally { setBusy(""); setRevision(value => value + 1); }
  }
  return <div className="space-y-6 min-w-0">
    <PageHeading title={titles[kind]} icon={kind === "clustering" ? Shapes : kind === "prediction" ? Sparkles : ChartNoAxesCombined} eyebrow="Mô hình & Dự báo" description={kind === "clustering" ? "Khám phá các nhóm tiêu thụ điện với K-Means và đánh giá Silhouette." : kind === "prediction" ? "Theo dõi dự báo tiêu thụ điện và chất lượng mô hình Random Forest." : "Phân loại mức tiêu thụ điện, xác suất và kết quả đánh giá mô hình."} />
    <Link href="/models" className="text-sm text-primary underline underline-offset-4">Mở Model Management — lịch sử tất cả mô hình</Link>
    <p className="text-sm text-muted-foreground">Bước 1: Huấn luyện mô hình từ dữ liệu hiện có. Bước 2: Chạy để xem kết quả. Huấn luyện lại sau khi cập nhật dữ liệu.</p>
    {admin ? <Panel title="Thao tác mô hình">
      <div className="flex flex-wrap items-end gap-3">{kind === "clustering" && <label className="space-y-1 text-sm"><span className="block">K tối đa (2–5, chọn theo Silhouette)</span><Input type="number" min={2} max={5} step={1} value={maxK} onChange={event => setMaxK(Number(event.target.value))} disabled={!!busy} className="w-32" /></label>}
        <Button disabled={!!busy} onClick={() => perform("train")}>{busy === "train" ? "Đang huấn luyện…" : "Huấn luyện"}</Button>
        <Button variant="outline" disabled={!!busy} onClick={() => perform("run")}>{busy === "run" ? "Đang chạy…" : "Chạy mô hình"}</Button>
      </div>
      {busy && <p role="status" className="text-sm">Yêu cầu đang được xử lý. Không gửi thêm lần nữa; nếu quá thời gian chờ, hãy kiểm tra lịch sử trước khi chạy lại.</p>}
    </Panel> : <p className="rounded-lg border border-border p-4 text-sm">Analyst có thể xem kết quả và lịch sử; chỉ Admin được huấn luyện hoặc chạy mô hình.</p>}
    {error && <p role="alert" className="rounded border border-destructive p-4 text-sm text-destructive">{error}</p>}
    {notice && <p role="status" className="text-sm text-emerald-700">{notice}</p>}
    <Panel title={selected ? `Chi tiết lượt #${selected}` : "Kết quả chạy gần nhất"} actions={<Button variant="outline" disabled={!!busy} onClick={() => { setRunView(initialModelRunViewState); setError(""); setRevision(value => value + 1); }}>Tải kết quả mới nhất</Button>}>
      {runView.status === "running" ? <p role="status" className="rounded-lg border border-border p-5 text-sm">Đang thực hiện {runView.action === "run" ? "lượt chạy" : "lượt huấn luyện"}. Kết quả của lượt trước được ẩn cho đến khi attempt này hoàn tất.</p>
        : runView.status === "failed" ? <div role="alert" className="rounded-lg border border-destructive/30 p-5 text-sm text-destructive"><p>Lượt {runView.action === "run" ? "chạy" : "huấn luyện"} thất bại. Không hiển thị kết quả cũ thay cho attempt này.</p><p className="mt-1">{runView.message}</p></div>
          : runView.status === "not_ready" ? <p role="status" className="rounded-lg border border-border p-5 text-sm">{runView.message} Kết quả cũ không được hiển thị như dự báo hiện tại.</p>
            : selected !== null && current.status === "success" && current.data && !modelRunDetailMatchesId(current.data, selected) ? <p role="alert" className="text-sm text-destructive">Gateway trả về chi tiết lượt không khớp ID được yêu cầu; không hiển thị kết quả này.</p>
              : kind === "clustering" ? <ClusteringResourceResult resource={current} />
              : <QueryState resource={current} empty="Chưa có kết quả chạy cho contract hiện tại. Admin hãy kiểm tra dữ liệu và artifact.">{run => {
                return <ModelResult run={run} requireH2 />;
              }}</QueryState>}
    </Panel>
    <Panel title="Lịch sử mô hình" actions={<Button variant="outline" onClick={() => setRevision(value => value + 1)}>Tải lại</Button>}>
      <QueryState resource={history}>{data => <div className="space-y-4">{!data.items.length ? <p role="status">Chưa có lịch sử.</p> : <DataTable caption="Lịch sử chạy mô hình" headers={["ID", "Giai đoạn", "Trạng thái", "Thời gian", "Chi tiết"]} rows={data.items.map(run => [run.id, String(run.parameters?.stage ?? "—"), <StatusBadge key="status" status={run.status} />, new Date(run.created_at).toLocaleString("vi-VN"), <Button key={run.id} size="sm" variant="outline" disabled={!!busy} onClick={() => { setError(""); setNotice(""); setRunView({ status: "idle", selectedRunId: run.id }); }}>Xem</Button>])} />}<Pagination page={page} pages={data.pages} total={data.total} onChange={setPage} /></div>}</QueryState>
    </Panel>
  </div>;
}
export function ModelWorkspace({ kind }: { kind: ModelKind }) { return <AppLayout><Workspace key={kind} kind={kind} /></AppLayout>; }
