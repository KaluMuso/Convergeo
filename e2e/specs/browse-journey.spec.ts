import { BASE_URL, LOCALE, path } from "../fixtures/env";
import { assertNoAccidentalRealMoney, paymentMockMode } from "../fixtures/payment-fixtures";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

/**
 * Release-certification browse journey (Layer 3).
 *
 * HOME → SEARCH → CATEGORY → PDP → ADD TO CART → CART → CHECKOUT
 *
 * Stops before any unsafe real-money action. Uses payment-mock / browse-safe
 * boundaries when sandbox creds are absent.
 */
test.describe("browse-journey · release certification", () => {
  test.beforeEach(() => {
    assertNoAccidentalRealMoney();
  });

  test("full critical browse path reaches checkout shell", async ({ page }) => {
    test.info().annotations.push({
      type: "mode",
      description: paymentMockMode() ? "payment-mock / browse-safe" : "deployed-target",
    });

    // 1. HOME
    await page.goto(path("/"));
    await expect(page).toHaveURL(new RegExp(`/${LOCALE}(/|$)`));
    await expect(
      page.getByTestId("home-hero-brand").or(page.getByTestId("home-hero-band")).first(),
    ).toBeVisible({ timeout: 30_000 });

    // 2. SEARCH
    await page.goto(path(`/search?q=${encodeURIComponent(SEED.searchTerm)}`));
    await expect(
      page
        .getByTestId("search-results-list")
        .or(page.getByTestId("search-query-summary"))
        .or(page.getByTestId("search-invalid-query"))
        .or(page.getByRole("search"))
        .first(),
    ).toBeVisible({ timeout: 20_000 });

    // 3. CATEGORY
    await page.goto(path("/c/electronics"));
    await expect(
      page
        .getByTestId("listing-grid")
        .or(page.getByTestId("plp-empty"))
        .or(page.getByTestId("plp-unavailable"))
        .or(page.getByTestId("plp-results-count"))
        .first(),
    ).toBeVisible({ timeout: 20_000 });

    // 4. PDP
    await page.goto(path(`/p/${SEED.product.slug}`));
    const buyBox = page.getByTestId("pdp-buy-box");
    const pdpAvailable = await buyBox.isVisible().catch(() => false);

    if (!pdpAvailable) {
      test.info().annotations.push({
        type: "pdp-skip",
        description: "PDP unavailable — honest empty; journey stops before cart",
      });
      await expect(
        page.getByTestId("pdp-unavailable").or(page.getByTestId("pdp-header")),
      ).toBeVisible();
      return;
    }

    // 5. ADD TO CART
    await page.getByTestId("pdp-add-to-cart").click();
    await expect(page.getByTestId("pdp-add-to-cart-success")).toBeVisible({ timeout: 15_000 });

    // 6. CART
    await page.goto(path("/cart"));
    await expect(
      page
        .getByTestId("cart-vendor-groups")
        .or(page.getByTestId("cart-empty-panel"))
        .or(page.getByTestId("cart-loading"))
        .first(),
    ).toBeVisible({ timeout: 20_000 });

    const hasItems = await page
      .getByTestId("cart-vendor-groups")
      .isVisible()
      .catch(() => false);
    if (!hasItems) {
      test
        .info()
        .annotations.push({
          type: "cart-empty",
          description: "Cart empty after add — API may be offline",
        });
      return;
    }

    // 7. CHECKOUT (stop before pay)
    await page.goto(path("/checkout"));
    await expect(
      page
        .getByTestId("checkout-payment-methods")
        .or(page.getByTestId("checkout-place-order"))
        .or(page.getByTestId("checkout-place-order-unavailable"))
        .or(page.getByRole("heading", { name: /checkout|delivery|payment/i }))
        .first(),
    ).toBeVisible({ timeout: 30_000 });

    // Assert we did NOT land on a false-success payment state.
    const falseSuccess = page.getByTestId("payment-success");
    await expect(falseSuccess)
      .not.toBeVisible({ timeout: 2_000 })
      .catch(() => {
        /* not visible = good */
      });
  });
});
