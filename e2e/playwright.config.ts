import { defineConfig, devices } from "@playwright/test";

import { BASE_URL } from "./fixtures/env";
import { CERTIFICATION_VIEWPORTS } from "./fixtures/viewports";

const isCI = !!process.env.CI;

/** Vercel Deployment Protection bypass for automation (header only — never in URLs). */
const bypassSecret = process.env.VERCEL_AUTOMATION_BYPASS_SECRET?.trim() ?? "";
const protectionHeaders: Record<string, string> = {};
if (bypassSecret) {
  protectionHeaders["x-vercel-protection-bypass"] = bypassSecret;
  protectionHeaders["x-vercel-set-bypass-cookie"] = "true";
}

/**
 * Use the pre-installed Chromium when `PW_CHROMIUM_PATH` is exported (this build
 * env pins it at /opt/pw-browsers/chromium so no browser download is triggered).
 * On GitHub-hosted CI the var is unset and Playwright uses its managed browser
 * installed via `playwright install chromium`.
 */
const executablePath = process.env.PW_CHROMIUM_PATH || undefined;

/** Build Playwright projects from certification viewport list. */
function viewportProjects() {
  return CERTIFICATION_VIEWPORTS.map((vp, index) => {
    const isPrimary = index === 0;
    return {
      name: isPrimary ? "mobile-fast-3g-360" : vp.name,
      use: {
        ...devices["Pixel 7"],
        viewport: { width: vp.width, height: vp.height },
        isMobile: vp.isMobile,
        hasTouch: vp.hasTouch,
      },
    };
  });
}

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
    ["json", { outputFile: "results/results.json" }],
  ],
  outputDir: "results/artifacts",
  use: {
    baseURL: BASE_URL,
    extraHTTPHeaders: protectionHeaders,
    trace: "on-first-retry",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    launchOptions: executablePath ? { executablePath } : {},
  },
  projects: viewportProjects(),
});
