import type { DemandPoint } from "./analysis-data";

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
    const response = await fetch(`${baseUrl.replace(/\/+$/, "")}/api/electricity/demand`, {
      signal: controller.signal, cache: "no-store", headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`API dữ liệu trả về lỗi HTTP ${response.status}.`);
    return parseDemandDataset(await response.json());
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
