import type { DemandPoint } from "./analysis-data";

export class DemandApiError extends Error {
  constructor(public status: number, message: string) { super(message); this.name = "DemandApiError"; }
}

export function resolveApiBase(baseUrl: string, browserHostname = typeof window === "undefined" ? "" : window.location.hostname) {
  const url = new URL(baseUrl);
  const local = ["localhost", "127.0.0.1"];
  // Keep local cookie requests same-site without changing remote API hosts.
  if (local.includes(url.hostname) && local.includes(browserHostname)) url.hostname = browserHostname;
  return url.toString().replace(/\/+$/, "");
}

export async function loginForDemand(email: string, password: string, baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000") {
  let response: Response;
  try {
    response = await fetch(`${resolveApiBase(baseUrl)}/api/auth/login`, {
      method: "POST", credentials: "include", cache: "no-store",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ email: email.trim(), password }), signal: AbortSignal.timeout(15000),
    });
  } catch {
    throw new Error("Không kết nối được API đăng nhập. Hãy kiểm tra backend và thử lại.");
  }
  if (response.status === 401) throw new DemandApiError(401, "Email hoặc mật khẩu không đúng, hoặc tài khoản đã bị vô hiệu hóa.");
  if (!response.ok) throw new DemandApiError(response.status, `Đăng nhập thất bại (HTTP ${response.status}).`);
}

export interface DemandDataset {
  source: string;
  country: string;
  iso3: "VNM";
  unit: "TWh";
  total: number;
  start_month: string | null;
  end_month: string | null;
  records: DemandPoint[];
}

export function parseDemandDataset(input: unknown): DemandDataset {
  const bad = () => { throw new Error("API trả về dữ liệu tiêu thụ không hợp lệ."); };
  if (!input || typeof input !== "object") return bad();
  const data = input as Record<string, unknown>;
  if (data.iso3 !== "VNM" || data.unit !== "TWh" || typeof data.source !== "string" || typeof data.country !== "string" || !Array.isArray(data.records)) return bad();
  const records: DemandPoint[] = [];
  const months = new Set<string>();
  for (const item of data.records) {
    if (!item || typeof item !== "object") return bad();
    const row = item as Record<string, unknown>;
    if (typeof row.month !== "string" || !/^[1-9]\d{3}-(0[1-9]|1[0-2])$/.test(row.month) || typeof row.value !== "number" || !Number.isFinite(row.value) || row.value < 0 || months.has(row.month)) return bad();
    months.add(row.month); records.push({ month: row.month, value: row.value });
  }
  records.sort((a, b) => a.month.localeCompare(b.month));
  const start = records[0]?.month ?? null, end = records.at(-1)?.month ?? null;
  if (data.total !== records.length || data.start_month !== start || data.end_month !== end) return bad();
  return { source: data.source, country: data.country, iso3: "VNM", unit: "TWh", total: records.length, start_month: start, end_month: end, records };
}

export async function fetchDemandDataset({ signal, baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000", timeoutMs = 15000 }: { signal?: AbortSignal; baseUrl?: string; timeoutMs?: number } = {}): Promise<DemandDataset> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const endpoint = `${resolveApiBase(baseUrl)}/api/electricity/demand`;
    let first: DemandDataset | null = null;
    let totalMatches: number | null = null;
    const records: DemandPoint[] = [];
    for (let page = 1; ; page++) {
      const response = await fetch(`${endpoint}?page=${page}&page_size=1000`, {
        signal: controller.signal, cache: "no-store", credentials: "include", headers: { Accept: "application/json" },
      });
      if (response.status === 401) throw new DemandApiError(401, "Bạn chưa đăng nhập hoặc phiên đăng nhập đã hết hạn.");
      if (response.status === 403) throw new DemandApiError(403, "Tài khoản không có quyền xem dữ liệu tiêu thụ.");
      if (!response.ok) throw new DemandApiError(response.status, `API dữ liệu trả về lỗi HTTP ${response.status}.`);
      const payload = await response.json();
      const current = parseDemandDataset(payload);
      const expected = payload.total_matches ?? current.total;
      if (!Number.isSafeInteger(expected) || expected < 0 || (payload.page !== undefined && payload.page !== page)) throw new Error("Thông tin phân trang API không hợp lệ.");
      if (!first) { first = current; totalMatches = expected; }
      if (expected !== totalMatches || current.source !== first.source || current.unit !== first.unit || current.country !== first.country) throw new Error("Dữ liệu API đã thay đổi giữa các trang. Vui lòng tải lại.");
      records.push(...current.records);
      if (records.length > expected) throw new Error("Số bản ghi API không khớp thông tin phân trang.");
      if (records.length === expected) break;
      if (!current.records.length) throw new Error("API thiếu dữ liệu ở trang tiếp theo.");
    }
    return parseDemandDataset({ ...first, records, total: records.length,
      start_month: records[0]?.month ?? null, end_month: records.at(-1)?.month ?? null });
  } catch (error) {
    if (signal?.aborted) throw error;
    if (timedOut) throw new Error("API phản hồi quá lâu. Vui lòng thử lại.");
    if (error instanceof TypeError) throw new Error("Không kết nối được API dữ liệu. Kiểm tra backend và địa chỉ NEXT_PUBLIC_API_URL.");
    if (error instanceof SyntaxError) throw new Error("API không trả về JSON hợp lệ.");
    throw error;
  } finally {
    clearTimeout(timer); signal?.removeEventListener("abort", abort);
  }
}
