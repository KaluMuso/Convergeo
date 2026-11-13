import { runDataQualityChecks } from "../fixtures/data-quality";
import { path, strictSyntheticRequired } from "../fixtures/env";
import { SEED, assertFixtureVersion } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

/**
 * Data-quality assertions on customer browse surfaces.
 * Differentiates legitimate free content from suspicious K0.00.
 */
test.describe("data-quality · browse surfaces", () => {
  test.beforeEach(async () => {
    if (strictSyntheticRequired()) {
      assertFixtureVersion();
    }
  });

  test("home and PLP pass data-quality scan", async ({ page }) => {
    await page.goto(path("/"));
    await page.waitForLoadState("domcontentloaded");
    let issues = await runDataQualityChecks(page);
    expect(issues, formatIssues(issues)).toHaveLength(0);

    await page.goto(path("/c/electronics"));
    await page.waitForLoadState("domcontentloaded");
    issues = await runDataQualityChecks(page);
    const plpIssues = issues.filter((i) =>
      ["unexpected_zero_price", "demo_badge_in_production", "wholesale_leakage"].includes(i.kind),
    );
    expect(plpIssues, formatIssues(plpIssues)).toHaveLength(0);
  });

  test("seeded PDP passes data-quality scan", async ({ page }) => {
    await page.goto(path(`/p/${SEED.product.slug}`));
    await page.waitForLoadState("domcontentloaded");

    const unavailable = await page
      .getByTestId("pdp-unavailable")
      .isVisible()
      .catch(() => false);
    if (unavailable && strictSyntheticRequired()) {
      throw new Error(`strictSyntheticRequired: seeded PDP ${SEED.product.slug} unavailable`);
    }

    const issues = await runDataQualityChecks(page);
    const blocking = issues.filter((i) => !(i.kind === "missing_product_image" && unavailable));
    expect(blocking, formatIssues(blocking)).toHaveLength(0);
  });

  test("search results pass price integrity scan", async ({ page }) => {
    await page.goto(path(`/search?q=${encodeURIComponent(SEED.searchTerm)}`));
    await page.waitForLoadState("domcontentloaded");

    const issues = await runDataQualityChecks(page);
    const priceIssues = issues.filter((i) =>
      ["unexpected_zero_price", "demo_badge_in_production", "wholesale_leakage"].includes(i.kind),
    );
    expect(priceIssues, formatIssues(priceIssues)).toHaveLength(0);
  });

  test("vendor storefront link resolves", async ({ page }) => {
    await page.goto(path(`/v/${SEED.vendor.slug}`));
    await page.waitForLoadState("domcontentloaded");

    const surface = page
      .getByTestId("listing-grid")
      .or(page.getByTestId("plp-empty"))
      .or(page.getByTestId("plp-unavailable"))
      .or(page.getByRole("heading"));
    const visible = await surface
      .first()
      .isVisible({ timeout: 20_000 })
      .catch(() => false);
    if (!visible) {
      if (strictSyntheticRequired()) {
        throw new Error(`strictSyntheticRequired: vendor ${SEED.vendor.slug} unreachable`);
      }
      test.info().annotations.push({
        type: "vendor-unavailable",
        description: "Vendor storefront not reachable without seed data",
      });
      return;
    }

    const issues = await runDataQualityChecks(page);
    expect(issues, formatIssues(issues)).toHaveLength(0);
  });
});

function formatIssues(issues: { kind: string; detail: string }[]): string {
  return issues.map((i) => `${i.kind}: ${i.detail}`).join("\n");
}
