import AxeBuilder from "@axe-core/playwright";
import type { Page as AxePage } from "playwright-core";

import { path } from "../fixtures/env";
import { expect, test } from "../fixtures/test-base";

/**
 * Cheap axe smoke for customer chrome (H10). Serious a11y regressions fail CI;
 * advisory rules can be tightened once staging content is stable.
 */
test.describe("a11y-smoke", () => {
  for (const route of ["/", "/cart", "/checkout"] as const) {
    test(`axe critical/serious on ${route}`, async ({ page }) => {
      await page.goto(path(route));
      await page.waitForLoadState("domcontentloaded");

      // axe-core pins playwright-core Page; @playwright/test Page is structurally compatible.
      const results = await new AxeBuilder({ page: page as unknown as AxePage })
        .withTags(["wcag2a", "wcag2aa"])
        .analyze();

      const blockers = results.violations.filter(
        (violation) => violation.impact === "critical" || violation.impact === "serious",
      );

      expect(blockers, blockers.map((v) => `${v.id}: ${v.help}`).join("\n")).toEqual([]);
    });
  }
});
