export class DemandApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message); this.name = "DemandApiError";
    if (status === 401 && typeof window !== "undefined") window.dispatchEvent(new Event("gateway-session-expired"));
  }
}

export function resolveApiBase(baseUrl: string, browserHostname = typeof window === "undefined" ? "" : window.location.hostname) {
  const url = new URL(baseUrl);
  if (["8101", "8102", "8103", "8104", "8105", "5433", "5435"].includes(url.port)) throw new Error("Frontend chỉ được kết nối API Gateway; hãy cấu hình NEXT_PUBLIC_API_URL=http://localhost:8001.");
  const local = ["localhost", "127.0.0.1"];
  if (local.includes(url.hostname) && local.includes(browserHostname)) url.hostname = browserHostname;
  return url.toString().replace(/\/+$/, "");
}

export async function loginForDemand(email: string, password: string, baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001") {
  let response: Response;
  try {
    response = await fetch(`${resolveApiBase(baseUrl)}/api/auth/login`, { method: "POST", credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify({ email: email.trim(), password }), signal: AbortSignal.timeout(15000) });
  } catch { throw new Error("Không kết nối được API đăng nhập. Hãy kiểm tra backend và thử lại."); }
  if (response.status === 401) throw new DemandApiError(401, "Email hoặc mật khẩu không đúng, hoặc tài khoản đã bị vô hiệu hóa.");
  if (!response.ok) throw new DemandApiError(response.status, `Đăng nhập thất bại (HTTP ${response.status}).`);
}

export interface NEMObservation {
  id: number; dataset_name: string; network_code: string; metric: string; interval: string; unit: string;
  observed_at: string; value: number; result: string; grouping_type: string; grouping_code: string; timezone: string;
}
export interface DemandDataset {
  dataset_name: string; network_code: "NEM"; metric: "demand"; interval: string; unit: string | null; timezone: "Australia/Brisbane";
  page: number; page_size: number; total_matches: number; coverage: Record<string, unknown>; records: NEMObservation[];
  start_date: string | null; end_date: string | null;
}

const isObject = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
const validDate = (value: string) => Number.isFinite(Date.parse(value));
const naturalKey = (row: Pick<NEMObservation, "observed_at" | "result" | "grouping_type" | "grouping_code">) => `${new Date(row.observed_at).toISOString()}|${row.result}|${row.grouping_type}|${row.grouping_code}`;
export function brisbaneDate(timestamp: string) {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Australia/Brisbane", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date(timestamp));
  const get = (type: string) => parts.find(part => part.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

export function parseDemandDataset(input: unknown): DemandDataset {
  const bad = (): never => { throw new Error("API trả về dữ liệu Open Electricity NEM không đúng cấu trúc."); };
  if (!isObject(input) || input.dataset_name !== "Open Electricity NEM" || input.network_code !== "NEM" || input.metric !== "demand" || typeof input.interval !== "string" || input.interval !== "1d" || (input.unit !== "MW" && input.unit !== null) || input.timezone !== "Australia/Brisbane" || !Number.isSafeInteger(input.page) || !Number.isSafeInteger(input.page_size) || !Number.isSafeInteger(input.total_matches) || (input.total_matches as number) < 0 || !isObject(input.coverage) || !Array.isArray(input.records)) return bad();
  const seenIds = new Set<number>(), seenNaturalKeys = new Set<string>();
  const records: NEMObservation[] = [];
  for (const raw of input.records) {
    if (!isObject(raw) || !Number.isSafeInteger(raw.id) || typeof raw.dataset_name !== "string" || raw.dataset_name !== input.dataset_name || raw.network_code !== "NEM" || raw.metric !== "demand" || raw.interval !== input.interval || raw.unit !== "MW" || typeof raw.observed_at !== "string" || !validDate(raw.observed_at) || !/(Z|[+-]\d{2}:\d{2})$/i.test(raw.observed_at) || typeof raw.value !== "number" || !Number.isFinite(raw.value) || raw.value < 0 || typeof raw.result !== "string" || typeof raw.grouping_type !== "string" || raw.grouping_type !== "network" || typeof raw.grouping_code !== "string" || raw.grouping_code !== "" || raw.timezone !== "Australia/Brisbane") return bad();
    const row = raw as unknown as NEMObservation;
    const key = naturalKey(row);
    if (seenIds.has(raw.id as number) || seenNaturalKeys.has(key)) return bad();
    seenIds.add(raw.id as number); seenNaturalKeys.add(key); records.push(row);
  }
  records.sort((a, b) => brisbaneDate(a.observed_at).localeCompare(brisbaneDate(b.observed_at)) || a.result.localeCompare(b.result));
  if (records.length > (input.page_size as number) || records.length > (input.total_matches as number)) return bad();
  return { dataset_name: input.dataset_name, network_code: "NEM", metric: "demand", interval: "1d", unit: input.unit as string | null, timezone: "Australia/Brisbane", page: input.page as number, page_size: input.page_size as number, total_matches: input.total_matches as number, coverage: input.coverage, records, start_date: records[0] ? brisbaneDate(records[0].observed_at) : null, end_date: records.at(-1) ? brisbaneDate(records.at(-1)!.observed_at) : null };
}

export async function fetchDemandDataset({ signal, baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001", timeoutMs = 15000 }: { signal?: AbortSignal; baseUrl?: string; timeoutMs?: number } = {}): Promise<DemandDataset> {
  const controller = new AbortController(); const abort = () => controller.abort();
  if (signal?.aborted) controller.abort(); signal?.addEventListener("abort", abort, { once: true });
  let timedOut = false; const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const endpoint = `${resolveApiBase(baseUrl)}/api/electricity/demand`;
    const records: NEMObservation[] = []; let first: DemandDataset | null = null; let total = 0;
    for (let page = 1; ; page++) {
      const response = await fetch(`${endpoint}?interval=1d&page=${page}&page_size=1000`, { signal: controller.signal, cache: "no-store", credentials: "include", headers: { Accept: "application/json" } });
      if (response.status === 401) throw new DemandApiError(401, "Bạn chưa đăng nhập hoặc phiên đăng nhập đã hết hạn.");
      if (response.status === 403) throw new DemandApiError(403, "Tài khoản không có quyền xem dữ liệu NEM.");
      if (!response.ok) throw new DemandApiError(response.status, `API dữ liệu NEM trả về lỗi HTTP ${response.status}.`);
      let payload: unknown; try { payload = await response.json(); } catch { throw new Error("API dữ liệu NEM không trả về JSON hợp lệ."); }
      const current = parseDemandDataset(payload);
      if (current.page !== page || current.page_size < current.records.length) throw new Error("Thông tin phân trang NEM không hợp lệ.");
      if (!first) { first = current; total = current.total_matches; }
      if (current.total_matches !== total || current.dataset_name !== first.dataset_name || current.interval !== first.interval || current.unit !== first.unit || current.timezone !== first.timezone) throw new Error("Metadata dữ liệu NEM thay đổi giữa các trang; vui lòng tải lại.");
      records.push(...current.records);
      if (records.length > total) throw new Error("Số bản ghi NEM vượt metadata phân trang.");
      if (records.length === total) break;
      if (!current.records.length) throw new Error("API thiếu dữ liệu ở trang tiếp theo; không thể xác nhận đã tải đủ.");
    }
    const uniqueRows = new Set(records.map(naturalKey));
    if (uniqueRows.size !== records.length) throw new Error("API trả bản ghi NEM trùng natural key giữa các trang.");
    return { ...first!, records, page: 1, page_size: Math.max(1000, records.length), total_matches: records.length, start_date: records[0] ? brisbaneDate(records[0].observed_at) : null, end_date: records.at(-1) ? brisbaneDate(records.at(-1)!.observed_at) : null };
  } catch (error) {
    if (signal?.aborted) throw error;
    if (timedOut) throw new Error("API NEM phản hồi quá lâu. Vui lòng thử lại.");
    if (error instanceof TypeError) throw new Error("Không kết nối được API NEM. Kiểm tra Gateway và NEXT_PUBLIC_API_URL.");
    throw error;
  } finally { clearTimeout(timer); signal?.removeEventListener("abort", abort); }
}
