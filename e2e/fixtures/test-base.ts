import { test as base, expect } from "@playwright/test";

import { bypassSecretForUrl, hasPortalSpecificBypass, THROTTLE } from "./env";
import { applyFast3G } from "./network";
import { verifyFixtureVersion } from "./seed";

type Fixtures = {
  /** Auto-fixture: applies Fast-3G throttling on the throttled project. */
  fast3g: void;
  /** Auto-fixture: per-origin Vercel Deployment Protection bypass. */
  portalBypass: void;
};

/**
 * Shared test object. Extends Playwright's base test with:
 *  - `fast3g` auto-fixture: emulates Fast-3G on Chromium for the throttled
 *    project (viewport/mobile flags come from the project `use` block).
 *  - `portalBypass` auto-fixture: sends the RIGHT project's Vercel protection
 *    bypass secret per origin (see below).
 */
export const test = base.extend<Fixtures>({
  /**
   * Vercel issues a "Protection Bypass for Automation" secret per project, and
   * specs navigate the vendor app on its own origin (vendor-sell,
   * event-ticket), so a single global header can be wrong for that origin.
   * `playwright.config.ts`'s `extraHTTPHeaders` still covers the common
   * single-secret setup; this fixture only engages when a portal-specific
   * secret is actually configured, rewriting the bypass header to match the
   * origin each request targets. Secrets are never logged or asserted on.
   */
  portalBypass: [
    async ({ context }, use) => {
      if (hasPortalSpecificBypass()) {
        await context.route("**/*", async (route) => {
          const secret = bypassSecretForUrl(route.request().url());
          if (!secret) {
            await route.fallback();
            return;
          }
          await route.fallback({
            headers: {
              ...route.request().headers(),
              "x-vercel-protection-bypass": secret,
              "x-vercel-set-bypass-cookie": "true",
            },
          });
        });
      }
      await use();
    },
    { auto: true },
  ],
  fast3g: [
    async ({ page, context }, use, testInfo) => {
      const wantsThrottle = THROTTLE && testInfo.project.name.toLowerCase().includes("3g");
      if (wantsThrottle) {
        try {
          const client = await context.newCDPSession(page);
          await applyFast3G(client);
        } catch {
          // Non-Chromium or CDP unavailable — skip throttling rather than fail.
        }
      }
      await use();
    },
    { auto: true },
  ],
});

export { expect };

/**
 * Record which fixture generation this worker is running against.
 *
 * NON-DESTRUCTIVE by design. This hook runs once per spec file per project — 16
 * files x 5 viewport projects — so the destructive reset that used to live here
 * fired ~80 times per run, with workers deleting rows other workers were
 * asserting on. The reset is now a single guarded workflow step before any
 * browser starts; all this does is observe.
 */
test.beforeAll(async () => {
  const verdict = verifyFixtureVersion();
  test.info().annotations.push({
    type: "fixture-version",
    description: verdict.ok
      ? "fixture generation verified (no destructive reset inside Playwright)"
      : (verdict.reason ?? "fixture version verification failed"),
  });
});
