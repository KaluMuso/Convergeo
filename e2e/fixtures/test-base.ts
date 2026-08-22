import { test as base, expect } from "@playwright/test";

import { bypassSecretForUrl, hasPortalSpecificBypass, THROTTLE } from "./env";
import { applyFast3G } from "./network";
import { resetSeed } from "./seed";

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
 * Run the deterministic seed reset once per worker before the specs execute.
 * Idempotent + a no-op (annotated) when the reset env is absent.
 */
test.beforeAll(async () => {
  const didReset = await resetSeed();
  test.info().annotations.push({
    type: "seed-reset",
    description: didReset
      ? "deterministic seed reset applied (idempotent)"
      : "seed reset skipped — E2E_SEED_RESET_URL/E2E_SEED_TOKEN not set (founder/staging-gated)",
  });
});
