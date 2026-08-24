import { defineConfig, devices } from "@playwright/test";

import { BASE_URL } from "./fixtures/env";
import {
  FAST_3G_PROJECT,
  RESPONSIVE_PROJECTS,
  specsForProject,
} from "./fixtures/spec-classification";
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

function viewportByName(name: string) {
  const vp = CERTIFICATION_VIEWPORTS.find((v) => v.name === name);
  if (!vp) {
    throw new Error(`playwright.config: no CERTIFICATION_VIEWPORTS entry named "${name}"`);
  }
  return vp;
}

/** testMatch for a project — driven entirely by fixtures/spec-classification.ts. */
function testMatchFor(projectName: string): string[] {
  const specs = specsForProject(projectName);
  if (specs.length === 0) {
    throw new Error(`playwright.config: project "${projectName}" has zero specs assigned`);
  }
  return [...specs];
}

/**
 * One project per certification viewport. RESPONSIVE_ALL_VIEWPORTS specs
 * (mobile-layout) run on all five; BEHAVIORAL_ONCE/PORTAL_SPECIFIC specs run
 * only on the canonical "mobile-390" project — see
 * fixtures/spec-classification.ts for the assignment logic.
 */
function responsiveProjects() {
  return RESPONSIVE_PROJECTS.map((name) => {
    const vp = viewportByName(name);
    return {
      name,
      testMatch: testMatchFor(name),
      use: {
        ...devices["Pixel 7"],
        viewport: { width: vp.width, height: vp.height },
        isMobile: vp.isMobile,
        hasTouch: vp.hasTouch,
      },
    };
  });
}

/**
 * Dedicated Fast-3G project (360×800, matching the LCP ≤2.5s Fast-3G/360px
 * budget in CLAUDE.md) — a separate identity from "mobile-360" on purpose.
 * The `fast3g` auto-fixture (fixtures/test-base.ts) throttles by matching
 * "3g" in `testInfo.project.name`, so a spec that must NOT be throttled
 * (mobile-layout's 360px run) cannot share a project with one that must be
 * (performance-smoke, clips-feed).
 */
function fast3gProject() {
  const vp = viewportByName("mobile-360");
  return {
    name: FAST_3G_PROJECT,
    testMatch: testMatchFor(FAST_3G_PROJECT),
    use: {
      ...devices["Pixel 7"],
      viewport: { width: vp.width, height: vp.height },
      isMobile: vp.isMobile,
      hasTouch: vp.hasTouch,
    },
  };
}

export default defineConfig({
  testDir: "./specs",
  // Whole-suite budget. The matrix shrank from 325 to 65 project-test
  // instances (PR B — removed the unscoped 5x spec×project fan-out and
  // mobile-layout's internal viewport loop); 720s is derived from run #47's
  // measured PASSING-test durations (p90 ≈17.3s/test × 65 tests / 2 CI
  // workers ≈562s, + the ≈64s observed pre-suite setup, + ~15% margin) —
  // see scripts/qa/self-test/e2e-matrix.test.mjs and the PR description.
  globalTimeout: 720 * 1000,
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
  projects: [...responsiveProjects(), fast3gProject()],
});
