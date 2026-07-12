import { defineConfig, devices } from "@playwright/test";

import { BASE_URL } from "./fixtures/env";

const isCI = !!process.env.CI;

/**
 * Use the pre-installed Chromium when `PW_CHROMIUM_PATH` is exported (this build
 * env pins it at /opt/pw-browsers/chromium so no browser download is triggered).
 * On GitHub-hosted CI the var is unset and Playwright uses its managed browser
 * installed via `playwright install chromium`.
 */
const executablePath = process.env.PW_CHROMIUM_PATH || undefined;

export default defineConfig({
  testDir: "./specs",
  // Whole-suite budget: keep the run under ~15 min on staging.
  globalTimeout: 15 * 60 * 1000,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  workers: isCI ? 2 : undefined,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
    ["junit", { outputFile: "results/junit.xml" }],
  ],
  outputDir: "results/artifacts",
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    launchOptions: executablePath ? { executablePath } : {},
  },
  projects: [
    {
      // Primary target: Zambian mobile-first — 360px viewport under Fast-3G.
      // The `fast3g` auto-fixture (fixtures/test-base) applies the throttle;
      // the project name contains "3g" so the fixture activates.
      name: "mobile-fast-3g-360",
      use: {
        ...devices["Pixel 7"],
        viewport: { width: 360, height: 780 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
});
