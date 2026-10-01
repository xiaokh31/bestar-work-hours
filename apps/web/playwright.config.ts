import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests", timeout: 90000, workers: 1,
  // Read-only checks may run against real attendance; never capture private records.
  use: {baseURL: process.env.TEST_WEB_URL ?? "http://localhost:3100", channel: process.platform === "win32" ? "msedge" : "chromium", trace: "off", screenshot: "off", video: "off"},
  reporter: [["list"], ["json", {outputFile:"test-results/results.json"}]],
});
