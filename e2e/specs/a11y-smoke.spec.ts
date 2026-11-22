import AxeBuilder from "@axe-core/playwright";
import type { Page as AxePage } from "playwright-core";

import { clickAddToCartAndAwaitOutcome } from "../fixtures/add-to-cart";
import { path } from "../fixtures/env";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

/**
 * Cheap axe smoke for customer chrome (H10). Serious a11y regressions fail CI;
 * advisory rules can be tightened once staging content is stable.
 */
async function runAxeSmoke(page: import("@playwright/test").Page) {
  // axe-core pins playwright-core Page; @playwright/test Page is structurally compatible.
  const results = await new AxeBuilder({ page: page as unknown as AxePage })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();

  const blockers = results.violations.filter(
    (violation) => violation.impact === "critical" || violation.impact === "serious",
  );

  expect(blockers, blockers.map((v) => `${v.id}: ${v.help}`).join("\n")).toEqual([]);
}

test.describe("a11y-smoke", () => {
  for (const route of ["/", "/cart"] as const) {
    test(`axe critical/serious on ${route}`, async ({ page }, testInfo) => {
      const expectedViewport = testInfo.project.metadata.perfA11yViewport;
      if (expectedViewport) expect(page.viewportSize()).toEqual(expectedViewport);
      await page.goto(path(route));
      await page.waitForLoadState("domcontentloaded");
      await runAxeSmoke(page);
    });
  }

  test("axe critical/serious on /checkout", async ({ page }, testInfo) => {
    const expectedViewport = testInfo.project.metadata.perfA11yViewport;
    if (expectedViewport) expect(page.viewportSize()).toEqual(expectedViewport);

    // Empty-cart client guard redirects during load; seed one item so axe runs on checkout.
    await page.goto(path(`/p/${SEED.product.slug}`));
    await clickAddToCartAndAwaitOutcome(page, testInfo, { timeout: 20_000 });
    await page.goto(path("/checkout"));
    await page.waitForURL(/\/checkout(?:\/|$|\?)/);
    await page.waitForLoadState("load");

    await runAxeSmoke(page);
  });
});
