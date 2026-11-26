import type { ModelKind } from "./gateway";

export type ModelAction = "train" | "run";

export type ModelRunViewState =
  | { status: "idle"; selectedRunId: number | null }
  | { status: "running"; action: ModelAction }
  | { status: "succeeded"; action: ModelAction; runId: number }
  | { status: "failed"; action: ModelAction; message: string }
  | { status: "not_ready"; message: string };

export const initialModelRunViewState: ModelRunViewState = {
  status: "idle",
  selectedRunId: null,
};

export function modelRunQueryPath(kind: ModelKind, state: ModelRunViewState): string | null {
  if (state.status === "running" || state.status === "failed" || state.status === "not_ready") return null;
  const runId = state.status === "succeeded" ? state.runId : state.selectedRunId;
  return runId === null ? "/api/" + kind + "/latest" : "/api/" + kind + "/runs/" + runId;
}

export function modelRunDetailMatchesId(run: { id?: unknown }, expectedRunId: number): boolean {
  return run.id === expectedRunId;
}

export function modelRunQueryKey(path: string | null, revision: number, attempt: number): string {
  return String(path) + "#" + revision + "#" + attempt;
}
