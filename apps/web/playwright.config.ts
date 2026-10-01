import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests", timeout: 90000, workers: 1,
  use: {baseURL: process.env.TEST_WEB_URL ?? "http://localhost:3100", channel: process.platform === "win32" ? "msedge" : "chromium", trace: "retain-on-failure"},
  reporter: [["list"], ["json", {outputFile:"test-results/results.json"}]],
});
