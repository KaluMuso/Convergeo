import { BASE_URL, LOCALE, path, strictSyntheticRequired } from "../fixtures/env";
import { assertNoAccidentalRealMoney, paymentMockMode } from "../fixtures/payment-fixtures";
import { SEED, assertFixtureVersion } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

/**
 * Release-certification browse journey (Layer 3).
 *
 * HOME → SEARCH → CATEGORY → PDP → ADD TO CART → CART → CHECKOUT
 *
 * Local exploratory mode may tolerate absent seed data.
 * Integrated staging / production-readiness MUST have synthetic fixtures —
 * missing PDP/vendor/cart fixtures fail (never PASS via skip).
 */
test.describe("browse-journey · release certification", () => {
  test.beforeEach(async () => {
    assertNoAccidentalRealMoney();
    if (strictSyntheticRequired()) {
      // The canonical seed already ran once, before any browser started. All
      // this asserts is that we are talking to that exact fixture generation.
      assertFixtureVersion();
    }
  });

  test("full critical browse path reaches checkout shell", async ({ page }) => {
    test.info().annotations.push({
      type: "mode",
      description: paymentMockMode() ? "payment-mock / browse-safe" : "deployed-target",
    });
    test.info().annotations.push({
      type: "base",
      description: BASE_URL,
    });

    // 1. HOME — Convergeo brand signal after #599
    await page.goto(path("/"));
    await expect(page).toHaveURL(new RegExp(`/${LOCALE}(/|$)`));
    await expect(
      page
        .getByTestId("brand-logo")
        .or(page.getByTestId("home-hero-brand"))
        .or(page.getByTestId("home-hero-band"))
        .first(),
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

    // 4. PDP (strict modes require buyable synthetic product)
    await page.goto(path(`/p/${SEED.product.slug}`));
    const buyBox = page.getByTestId("pdp-buy-box");
    const pdpAvailable = await buyBox.isVisible().catch(() => false);

    if (!pdpAvailable) {
      if (strictSyntheticRequired()) {
        throw new Error(
          `strictSyntheticRequired: seeded PDP ${SEED.product.slug} unavailable — FAIL (not PASS)`,
        );
      }
      test.info().annotations.push({
        type: "pdp-skip",
        description: "PDP unavailable — local exploratory; journey stops before cart",
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
      if (strictSyntheticRequired()) {
        throw new Error("strictSyntheticRequired: cart empty after add-to-cart — FAIL");
      }
      test.info().annotations.push({
        type: "cart-empty",
        description: "Cart empty after add — local exploratory",
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

    const falseSuccess = page.getByTestId("payment-success");
    await expect(falseSuccess).toBeHidden({ timeout: 2_000 });
  });
});
