const labels: Record<string, string> = { completed: "Hoàn tất", failed: "Thất bại", queued: "Đang chờ", running: "Đang chạy", uploaded: "Đã upload", imported: "Đã import", active: "Hoạt động", ready: "Sẵn sàng", pending: "Đang chờ", success: "Thành công" };
export function StatusBadge({ status }: { status: string }) {
  const tone = ["completed", "imported", "active", "ready", "success"].includes(status) ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : ["failed", "error"].includes(status) ? "bg-rose-500/10 text-rose-700 dark:text-rose-300" : ["running", "queued", "pending"].includes(status) ? "bg-amber-500/10 text-amber-800 dark:text-amber-300" : "bg-blue-500/10 text-blue-700 dark:text-blue-300";
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium whitespace-nowrap ${tone}`}><span aria-hidden="true" className="size-1.5 rounded-full bg-current" />{labels[status] ?? status}</span>;
}
