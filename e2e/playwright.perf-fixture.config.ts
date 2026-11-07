import { chromium, defineConfig, devices } from "@playwright/test";

/** Only the disposable Actions fixture; never inherits a private browser override. */
export default defineConfig({
  testDir: "./specs",
  testMatch: "perf-fixture-content.spec.ts",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  forbidOnly: true,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: "results/perf-fixture-content",
  use: {
    ...devices["Pixel 7"],
    viewport: { width: 360, height: 800 },
    baseURL: "http://localhost:3000",
    browserName: "chromium",
    ignoreHTTPSErrors: false,
    bypassCSP: false,
    trace: "off",
    video: "off",
    screenshot: "off",
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    launchOptions: {
      executablePath: chromium.executablePath(),
      chromiumSandbox: true,
    },
  },
  projects: [{ name: "perf-fixture-chromium-141" }],
});
