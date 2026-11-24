import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";

const gateway = (process.env.E2E_API_URL || "http://localhost:8001").replace(/\/$/, "");
const writes = process.env.E2E_EXERCISE_WRITES === "1";

test("real browser → Gateway → services: Admin and Analyst handover", async ({ page, context }) => {
  const adminEmail = process.env.E2E_ADMIN_EMAIL;
  const adminPassword = process.env.E2E_ADMIN_PASSWORD;
  const analystEmail = process.env.E2E_ANALYST_EMAIL;
  const analystPassword = process.env.E2E_ANALYST_PASSWORD;
  if (!adminEmail || !adminPassword) throw new Error("Configure E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD locally. No credentials are included in source.");
  if (writes && (!analystEmail || !analystPassword || analystPassword.length < 12)) throw new Error("Write-flow tests require E2E_ANALYST_EMAIL and E2E_ANALYST_PASSWORD (12+ characters).");
  const directServiceRequests = [];
  page.on("request", request => { const target = new URL(request.url()); if (["8101", "8102", "8103", "8104", "8105", "5433"].includes(target.port)) directServiceRequests.push(target.origin); });

  async function login(email, password) {
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Mật khẩu", { exact: true }).fill(password);
    const response = page.waitForResponse(response => new URL(response.url()).pathname === "/api/auth/login" && response.request().method() === "POST");
    await page.getByRole("button", { name: "Đăng nhập và tải biểu đồ", exact: true }).click();
    expect((await response).status()).toBe(200);
    await expect(page.getByRole("button", { name: "Đăng xuất", exact: true })).toBeVisible();
  }
  async function checkPage(path, heading) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  }
  async function checkModelManagement() {
    await checkPage("/models", "Model Management");
    const filtered = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname === "/api/model-runs" && url.searchParams.get("model_type") === "prediction" && url.searchParams.get("status") === "completed";
    });
    await page.getByLabel("Loại mô hình", { exact: true }).selectOption("prediction");
    await page.getByLabel("Trạng thái lượt chạy", { exact: true }).selectOption("completed");
    const response = await filtered; expect(response.status()).toBe(200);
    const data = await response.json(); expect(data.items.length).toBeGreaterThan(0);
    expect(data.items.every(run => run.model_type === "prediction" && run.status === "completed")).toBe(true);
    const runId = data.items[0].id;
    const detail = page.waitForResponse(response => new URL(response.url()).pathname === `/api/model-runs/${runId}`);
    await page.getByRole("button", { name: `Xem lượt #${runId}`, exact: true }).click();
    expect((await detail).status()).toBe(200);
    await expect(page.getByRole("heading", { name: `Chi tiết lượt #${runId}`, exact: true })).toBeVisible();
  }
  await page.goto("/login");
  await login(adminEmail, adminPassword);
  expect((await context.request.get(gateway + "/api/auth/me")).status()).toBe(200);
  await checkPage("/", "Overview Dashboard");
  await expect(page.getByText("Đang tải kết quả phân tích…")).toHaveCount(0);
  await expect(page.locator(".recharts-surface").first()).toBeVisible();
  await checkPage("/analysis/consumption", "Consumption Analysis");
  await page.getByLabel("Gộp dữ liệu").selectOption("quarter");
  await expect(page.getByText(/\d{4}-Q[1-4]/).first()).toBeVisible();
  const csvDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Xuất CSV", exact: true }).first().click();
  const csvFile = await csvDownload;
  expect(csvFile.suggestedFilename()).toMatch(/\.csv$/);
  expect(await readFile(await csvFile.path(), "utf8")).toContain("TWh");
  const distribution = page.waitForResponse(response => new URL(response.url()).pathname === "/api/analysis/distribution" && new URL(response.url()).searchParams.get("bins") === "5");
  await page.getByLabel("Số khoảng phân bố").selectOption("5");
  expect((await distribution).status()).toBe(200);
  await checkPage("/analysis/trend", "Trend & Seasonality");
  const trend = page.waitForResponse(response => new URL(response.url()).pathname === "/api/analysis/trend" && new URL(response.url()).searchParams.get("window_months") === "3");
  await page.getByLabel("Cửa sổ trung bình trượt").selectOption("3");
  expect((await trend).status()).toBe(200);
  await checkPage("/analysis/correlation", "Correlation");
  await expect(page.getByRole("heading", { name: "Ma trận Pearson từ API" })).toBeVisible();

  if (writes) {
    await checkPage("/settings", "Cài đặt & Tài khoản");
    const search = await context.request.get(gateway + "/api/users?search=" + encodeURIComponent(analystEmail) + "&page_size=100");
    expect(search.status()).toBe(200);
    const existing = (await search.json()).items.find(user => user.email.toLowerCase() === analystEmail.toLowerCase());
    if (!existing) {
      await page.getByLabel("Tên người dùng", { exact: true }).fill("analyst_e2e_" + randomUUID().slice(0, 8));
      await page.getByLabel("Email", { exact: true }).fill(analystEmail);
      await page.getByLabel("Mật khẩu (12–128 ký tự)", { exact: true }).fill(analystPassword);
      await page.getByLabel("Nhập lại mật khẩu", { exact: true }).fill(analystPassword);
      await page.getByLabel("Vai trò tài khoản mới").selectOption("analyst");
      const create = page.waitForResponse(response => new URL(response.url()).pathname === "/api/users" && response.request().method() === "POST");
      await page.getByRole("button", { name: "Tạo tài khoản", exact: true }).click();
      expect((await create).status()).toBe(201);
    } else {
      expect(existing.role).toBe("analyst"); expect(existing.is_active).toBe(true);
    }
    await checkPage("/ingestion", "Data Management");
    const datasetName = "Browser E2E " + randomUUID();
    await page.getByLabel("Tên dataset", { exact: true }).fill(datasetName);
    await page.getByLabel("Nguồn", { exact: true }).fill("project-csv-browser-check");
    await page.getByLabel("File CSV (tối đa 25 MB)", { exact: true }).setInputFiles(fileURLToPath(new URL("../../data/processed/vietnam_electricity_demand.csv", import.meta.url)));
    const upload = page.waitForResponse(response => new URL(response.url()).pathname === "/api/datasets/upload");
    await page.getByRole("button", { name: "Upload CSV", exact: true }).click();
    const uploaded = await upload; expect(uploaded.status()).toBe(201);
    const dataset = await uploaded.json();
    const imported = page.waitForResponse(response => new URL(response.url()).pathname === `/api/datasets/${dataset.id}/import`);
    await page.getByRole("row").filter({ hasText: datasetName }).getByRole("button", { name: "Import", exact: true }).click();
    expect((await imported).status()).toBe(200);
    await expect(page.getByRole("heading", { name: `Lịch sử dataset #${dataset.id}` })).toBeVisible();
    await expect(page.getByRole("heading", { name: `Chi tiết dataset #${dataset.id}` })).toBeVisible();
    await expect(page.locator("dd").filter({ hasText: datasetName })).toBeVisible();
    // Validate a rejected upload through the actual Ingestion Service, without routing mocks.
    await page.getByLabel("Tên dataset", { exact: true }).fill(datasetName + " invalid");
    await page.getByLabel("File CSV (tối đa 25 MB)", { exact: true }).setInputFiles({ name: "invalid.csv", mimeType: "text/csv", buffer: Buffer.from("invalid,columns\n1,2") });
    const invalid = page.waitForResponse(response => new URL(response.url()).pathname === "/api/datasets/upload");
    await page.getByRole("button", { name: "Upload CSV", exact: true }).click();
    expect([400, 415, 422]).toContain((await invalid).status());
    await expect(page.getByRole("alert")).toBeVisible();
    for (const [kind, heading] of [["clustering", "Phân cụm tiêu thụ"], ["prediction", "Dự báo nhu cầu"], ["classification", "Phân loại tiêu thụ"]]) {
      await checkPage("/" + kind, heading);
      for (const [action, label] of [["train", "Huấn luyện"], ["run", "Chạy mô hình"]]) {
        const response = page.waitForResponse(response => new URL(response.url()).pathname === `/api/${kind}/${action}` && response.request().method() === "POST", { timeout: 200000 });
        await page.getByRole("button", { name: label, exact: true }).click();
        expect((await response).status()).toBe(200);
        await expect(page.getByRole("button", { name: "Chạy mô hình", exact: true })).toBeEnabled({ timeout: 200000 });
        await expect(page.getByRole("alert")).toHaveCount(0);
      }
      await expect(page.getByRole("heading", { name: "Lịch sử mô hình" })).toBeVisible();
    }
    await checkModelManagement();
    await page.getByRole("button", { name: "Đăng xuất", exact: true }).click();
    await login(analystEmail, analystPassword);
    expect((await context.request.get(gateway + "/api/auth/me")).status()).toBe(200);
    for (const [kind, heading] of [["clustering", "Phân cụm tiêu thụ"], ["prediction", "Dự báo nhu cầu"], ["classification", "Phân loại tiêu thụ"]]) {
      await checkPage("/" + kind, heading);
      await expect(page.getByRole("button", { name: "Huấn luyện", exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Chạy mô hình", exact: true })).toHaveCount(0);
      expect((await context.request.post(gateway + `/api/${kind}/run`)).status()).toBe(403);
    }
    await checkPage("/settings", "Cài đặt & Tài khoản");
    await expect(page.getByRole("button", { name: "Tạo tài khoản", exact: true })).toHaveCount(0);
    expect((await context.request.get(gateway + "/api/users")).status()).toBe(403);
    await checkModelManagement();
    await checkPage("/ingestion", "Data Management");
    await expect(page.getByRole("button", { name: "Upload CSV", exact: true })).toHaveCount(0);
    expect((await context.request.post(gateway + "/api/datasets/sync")).status()).toBe(403);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await checkPage("/", "Overview Dashboard");
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  expect(directServiceRequests).toEqual([]);
  await page.getByRole("button", { name: "Đăng xuất", exact: true }).click();
  await expect(page.getByRole("button", { name: "Đăng nhập và tải biểu đồ", exact: true })).toBeVisible();
  expect((await context.request.get(gateway + "/api/auth/me")).status()).toBe(401);
});
