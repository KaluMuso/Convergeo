import { test as base, expect } from "@playwright/test";

import { THROTTLE } from "./env";
import { applyFast3G } from "./network";
import { resetSeed } from "./seed";

type Fixtures = {
  /** Auto-fixture: applies Fast-3G throttling on the throttled project. */
  fast3g: void;
};

/**
 * Shared test object. Extends Playwright's base test with:
 *  - `fast3g` auto-fixture: emulates Fast-3G on Chromium for the throttled
 *    project (viewport/mobile flags come from the project `use` block).
 */
export const test = base.extend<Fixtures>({
  fast3g: [
    async ({ page, context }, use, testInfo) => {
      const wantsThrottle =
        THROTTLE && testInfo.project.name.toLowerCase().includes("3g");
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
