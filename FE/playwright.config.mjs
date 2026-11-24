import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e", testMatch: "**/*.spec.mjs", workers: 1, fullyParallel: false,
  timeout: 600000, expect: { timeout: 20000 },
  outputDir: "test-results/browser",
  reporter: [["list"], ["json", { outputFile: "test-results/browser-results.json" }]],
  use: { baseURL: process.env.E2E_FE_URL || "http://localhost:3000", browserName: "chromium", headless: true, viewport: { width: 1280, height: 900 }, trace: "off", video: "off", screenshot: "only-on-failure" },
});
