import { defineConfig, devices } from "@playwright/test";

import { BASE_URL, certificationMode } from "./fixtures/env";
import {
  FAST_3G_PROJECT,
  RESPONSIVE_PROJECTS,
  specsForProject,
} from "./fixtures/spec-classification";
import { CERTIFICATION_VIEWPORTS } from "./fixtures/viewports";
import { resolveWorkers } from "./fixtures/worker-policy";

const isCI = !!process.env.CI;

/**
 * Vercel Deployment Protection bypass is deliberately ABSENT from this file.
 *
 * `extraHTTPHeaders` is a CONTEXT-level header set: Playwright attaches it to
 * every request the browser makes, portal or not. Injecting the bypass secret
 * here therefore sent a Vercel credential to Supabase, the staging FastAPI,
 * Cloudinary, fonts, analytics — every origin a page happened to touch.
 *
 * There is now exactly ONE browser injection mechanism: the origin-aware
 * `portalBypass` fixture in fixtures/test-base.ts, which resolves the right
 * project's secret per origin (portal-specific first, then the legacy
 * repository-wide `VERCEL_AUTOMATION_BYPASS_SECRET`) and attaches nothing at
 * all to an unmatched origin. The legacy secret is still fully supported —
 * it is just routed per origin instead of broadcast.
 *
 * scripts/qa/self-test/e2e-portal-bypass.test.mjs fails if a bypass header
 * reappears in this file.
 */

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
  /**
   * Worker count comes from fixtures/worker-policy.ts: 1 in a strict
   * certification run (integrated-staging / production-readiness), 2 in
   * ordinary CI, Playwright's default locally. The real checkout specs share
   * one synthetic Customer whose cart the API resolves by owner, so two
   * workers could interleave one buyer's cart/reservation state. Everything
   * else here -- fullyParallel, retries, the per-test timeout, globalTimeout,
   * the projects, the viewports and the spec assignment -- is unchanged.
   */
  workers: resolveWorkers({ isCI, mode: certificationMode() }),
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
    ["junit", { outputFile: "results/junit.xml" }],
    ["json", { outputFile: "results/results.json" }],
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
  projects: [...responsiveProjects(), fast3gProject()],
});
