import { path, strictSyntheticRequired } from "../fixtures/env";
import { installMockBuyerSession } from "../fixtures/payment-fixtures";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

/**
 * UX surface coverage: wishlist, compare, vendor storefront, offline/error,
 * order-history fixture (signed-out boundary).
 */
test.describe("ux-surfaces · release certification", () => {
  test("wishlist page renders honest empty or items", async ({ page }) => {
    await page.goto(path("/wishlist"));
    await page.waitForLoadState("domcontentloaded");
    await expect(
      page
        .getByTestId("saved-items-empty")
        .or(page.getByTestId("saved-items-list"))
        .or(page.getByTestId("saved-items-loading"))
        .first(),
    ).toBeVisible({ timeout: 20_000 });
  });

  test("compare page renders comparison or empty state", async ({ page }) => {
    await page.goto(path(`/p/${SEED.product.slug}`));
    const compareEntry = page.getByTestId("pdp-compare-entry");
    if (await compareEntry.isVisible().catch(() => false)) {
      await compareEntry.click();
    } else {
      await page.goto(path("/compare"));
    }
    await page.waitForLoadState("domcontentloaded");
    await expect(
      page
        .getByTestId("pdp-comparison")
        .or(page.getByTestId("pdp-compare-cards"))
        .or(page.getByRole("heading", { name: /compare/i }))
        .first(),
    ).toBeVisible({ timeout: 20_000 });
  });

  test("vendor storefront renders catalog surface", async ({ page }) => {
    await page.goto(path(`/v/${SEED.vendor.slug}`));
    await page.waitForLoadState("domcontentloaded");
    const surface = page
      .getByTestId("listing-grid")
      .or(page.getByTestId("plp-empty"))
      .or(page.getByTestId("plp-unavailable"))
      .or(page.getByRole("heading", { name: /E2E Test Vendor|vendor|store/i }));
    // isVisible({ timeout }) does NOT wait/retry despite the option — it is
    // an instant DOM sample, so this raced the storefront's render and
    // misclassified a fully-rendered catalog surface as missing (E2E run #52,
    // RC-5: the failing attempt's own snapshot showed the complete storefront
    // — heading, KYC badge, product tab, 3 products). waitFor() genuinely
    // polls until the deadline.
    const visible = await surface
      .first()
      .waitFor({ state: "visible", timeout: 20_000 })
      .then(() => true)
      .catch(() => false);
    if (!visible && strictSyntheticRequired()) {
      throw new Error(`strictSyntheticRequired: vendor ${SEED.vendor.slug} surface missing`);
    }
    expect(visible).toBe(true);
  });

  test("offline page shows recovery affordance", async ({ page }) => {
    await page.goto(path("/offline"));
    await page.waitForLoadState("domcontentloaded");
    await expect(page.getByRole("button", { name: /retry|reload|try again/i }).first()).toBeVisible(
      {
        timeout: 15_000,
      },
    );
  });

  test("order history redirects or shows sign-in boundary", async ({ page }) => {
    await page.goto(path("/account/orders"));
    await page.waitForLoadState("domcontentloaded");
    // Do not treat bare <main> as success — require auth/account signal.
    await expect(
      page
        .getByRole("link", { name: /sign in|log in|phone/i })
        .or(page.getByTestId("account-overview"))
        .or(page.getByRole("heading", { name: /order|account|sign/i }))
        .first(),
    ).toBeVisible({ timeout: 20_000 });
  });

  test("returns/dispute help surface is reachable", async ({ page }) => {
    await page.goto(path("/legal/returns"));
    await page.waitForLoadState("domcontentloaded");
    await expect(page.getByRole("heading").first()).toBeVisible({ timeout: 15_000 });
  });

  test("error state on invalid PDP is honest", async ({ page }) => {
    await page.goto(path("/p/this-product-definitely-does-not-exist-xyz"));
    await page.waitForLoadState("domcontentloaded");
    // A genuinely nonexistent slug hits fetchProduct's "not_found" branch, which
    // calls Next's notFound() and renders app/[locale]/not-found.tsx — copy is
    // "We can't find that page" (marketing.notFound.heading), not "not found" /
    // "no longer". "unavailable" alone still covers the in-page PDP "unavailable"
    // state (catalog.pdp.unavailableTitle: "Product unavailable").
    await expect(
      page
        .getByTestId("pdp-unavailable")
        .or(
          page.getByRole("heading", {
            name: /not found|unavailable|no longer|can't find|can’t find/i,
          }),
        )
        .first(),
    ).toBeVisible({ timeout: 20_000 });
  });

  test("signup/login sandbox fixture boundary", async ({ page }) => {
    await installMockBuyerSession(page);
    await page.goto(path("/account"));
    await page.waitForLoadState("domcontentloaded");
    await expect(
      page
        .getByTestId("account-overview")
        .or(page.getByRole("link", { name: /sign in|log in|phone/i }))
        .or(page.getByRole("heading", { name: /account|sign/i }))
        .first(),
    ).toBeVisible({ timeout: 20_000 });
  });
});
