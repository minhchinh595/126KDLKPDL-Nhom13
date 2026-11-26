import { DemandApiError, resolveApiBase } from "./demand-api";

export type Role = "admin" | "analyst";
export interface User { id: number; username: string; email: string; role: Role; is_active: boolean }
export type ModelKind = "clustering" | "prediction" | "classification";
export interface ModelRun { id: number; model_type: ModelKind; status: "queued" | "running" | "completed" | "failed"; created_at: string; started_at: string | null; completed_at: string | null; parameters: Record<string, unknown> | null; metrics: Record<string, unknown> | null; error_message: string | null }
export interface PageResult<T> { items: T[]; page: number; page_size: number; total: number; pages: number }
export interface Dataset { id: number; name: string; source: string; file_name: string; description: string | null; record_count: number; start_date: string | null; end_date: string | null; status: string; source_role: "active_nem" | "legacy"; created_at: string; updated_at: string }
export interface ImportHistory { id: number; dataset_id: number; mode: string; status: string; rows_read: number; inserted_count: number; updated_count: number; skipped_count: number; error_count: number; error_message: string | null; started_at: string; completed_at: string | null }
export interface ImportResult { dataset: Dataset; history: ImportHistory }
export const gatewayBase = () => resolveApiBase(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001");

export async function gatewayRequest<T>(path: string, { method = "GET", body, signal, timeoutMs = 15000, baseUrl }: { method?: string; body?: unknown; signal?: AbortSignal; timeoutMs?: number; baseUrl?: string } = {}): Promise<T> {
  if (!path.startsWith("/api/") || path.includes("://") || path.split("?")[0].split("/").includes("..")) throw new Error("Đường dẫn Gateway không hợp lệ.");
  const form = typeof FormData !== "undefined" && body instanceof FormData;
  const combined = signal ? AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)]) : AbortSignal.timeout(timeoutMs);
  let response: Response;
  try {
    response = await fetch((baseUrl ? resolveApiBase(baseUrl) : gatewayBase()) + path, { method, signal: combined, credentials: "include", cache: "no-store", headers: form ? { Accept: "application/json" } : { Accept: "application/json", ...(body !== undefined ? { "Content-Type": "application/json" } : {}) }, body: body === undefined ? undefined : form ? body as FormData : JSON.stringify(body) });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new Error(combined.aborted ? "Yêu cầu quá thời gian chờ. Hãy tải lại kết quả trước khi thao tác lần nữa." : "Không kết nối được Gateway. Kiểm tra dịch vụ tại cổng 8001.");
  }
  if (!response.ok) {
    let detail: unknown;
    try { detail = (await response.json()).detail; } catch { /* HTTP status remains available. */ }
    const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((entry: { loc?: unknown[]; msg?: string }) => `${entry.loc?.join(".") ?? ""}: ${entry.msg ?? "Không hợp lệ"}`).join("; ") : detail && typeof detail === "object" && typeof (detail as Record<string, unknown>).message === "string" ? String((detail as Record<string, unknown>).message) : `Gateway trả lỗi HTTP ${response.status}.`;
    throw new DemandApiError(response.status, response.status === 401 ? "Phiên đăng nhập đã hết hạn." : response.status === 403 ? "Tài khoản không có quyền thực hiện thao tác này." : message, detail);
  }
  if (response.status === 204) return undefined as T;
  try { return await response.json() as T; } catch { throw new Error("Gateway trả về dữ liệu không hợp lệ."); }
}
export function parseUser(input: unknown): User {
  if (!input || typeof input !== "object") throw new Error("Thông tin phiên đăng nhập không hợp lệ.");
  const user = input as User;
  if (!Number.isSafeInteger(user.id) || typeof user.username !== "string" || typeof user.email !== "string" || !["admin", "analyst"].includes(user.role) || user.is_active !== true) throw new Error("Tài khoản không hợp lệ hoặc đã bị vô hiệu hóa.");
  return user;
}
export function canManage(role: Role) { return role === "admin"; }
export function query(params: Record<string, string | number | boolean | undefined>) { const search = new URLSearchParams(); for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== "") search.set(key, String(value)); return search.size ? `?${search}` : ""; }

export function modelRunsPath({ modelType = "", status = "", order = "desc", page = 1, pageSize = 10 }: { modelType?: ModelKind | ""; status?: ModelRun["status"] | ""; order?: "asc" | "desc"; page?: number; pageSize?: number } = {}) {
  if ((modelType && !["clustering", "prediction", "classification"].includes(modelType)) || (status && !["queued", "running", "completed", "failed"].includes(status)) || !["asc", "desc"].includes(order) || !Number.isInteger(page) || page < 1 || !Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) throw new Error("Bộ lọc lịch sử mô hình không hợp lệ.");
  return "/api/model-runs" + query({ model_type: modelType, status, order, page, page_size: pageSize });
}
export function modelActionPath(kind: ModelKind, action: "train" | "run", maxK = 5) {
  if (!["clustering", "prediction", "classification"].includes(kind) || !["train", "run"].includes(action)) throw new Error("Thao tác mô hình không được hỗ trợ.");
  if (kind === "clustering" && action === "train" && (!Number.isInteger(maxK) || maxK < 2 || maxK > 5)) throw new Error("K tối đa phải là số nguyên từ 2 đến 5.");
  return `/api/${kind}/${action}` + (kind === "clustering" && action === "train" ? query({ max_k: maxK }) : "");
}
