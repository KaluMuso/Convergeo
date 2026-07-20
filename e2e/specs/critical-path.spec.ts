import { lenco, path } from "../fixtures/env";
import { sandboxEnabled } from "../fixtures/lenco";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

/**
 * VE-P07 · G16 — Critical-path happy E2E (distinct file from VB-P07's
 * checkout-false-success.spec.ts).
 *
 * Journey: home → search/PLP → PDP → add to cart → cart total → checkout
 * (MoMo, mobile-money-first) → Lenco sandbox pay → order confirmation. Runs on
 * the Fast-3G / 360px project (the suite's only project — Zambian mobile bar).
 *
 * The pre-payment journey is CREDENTIAL-FREE against any live target. The
 * sandbox charge + confirmation legs are ENV-GATED behind `LENCO_SANDBOX` +
 * creds (founder gate F9b): absent creds the spec asserts up to the
 * pay-initiation boundary and skips with an annotation — it never hammers a
 * real payment endpoint. False-success paths are VB-P07's file, not this one.
 */
test.describe("shop · critical-path (G16)", () => {
  test("browse → search → PDP → cart → sandbox checkout → order confirmation", async ({ page }) => {
    // 1. Land on home — the discovery surface must render.
    await page.goto(path("/"));
    await expect(
      page.getByTestId("home-category-grid").or(page.getByTestId("home-trust-strip")),
    ).toBeVisible();

    // 2. Search/PLP for the seeded, buyable product.
    await page.goto(path(`/search?q=${encodeURIComponent(SEED.searchTerm)}`));
    await expect(page.getByTestId("search-results-list")).toBeVisible();

    // 3. PDP: buy box + ZMW price render.
    await page.goto(path(`/p/${SEED.product.slug}`));
    await expect(page.getByTestId("pdp-buy-box")).toBeVisible();
    await expect(page.getByTestId("pdp-price")).toBeVisible();

    // 4. Add to cart.
    await page.getByTestId("pdp-add-to-cart").click();
    await expect(page.getByTestId("pdp-add-to-cart-success")).toBeVisible();

    // 5. Cart holds the line with a subtotal (fails loudly on a wrong total
    //    surface: an empty cart here means the add-to-cart leg lied).
    await page.goto(path("/cart"));
    await expect(page.getByTestId("cart-page")).toBeVisible();
    await expect(page.getByTestId("cart-subtotal")).toBeVisible();
    await expect(page.getByTestId("cart-empty-state")).toHaveCount(0);

    // 6. Checkout — choose MoMo (USSD push), the mobile-money-first rail.
    await page.goto(path("/checkout"));
    const momo = page.locator('[name="payment-method"][value="momo"]');
    await momo
      .first()
      .check()
      .catch(async () => {
        // Fallback: some renders expose MoMo as the rail select rather than radio.
        await page.locator('[name="momo-rail"]').first().waitFor();
      });

    // Payer contact — the sandbox auto-approve MSISDN when available.
    const phoneField = page.getByLabel(/phone|mobile|momo/i).first();
    if (await phoneField.count()) {
      await phoneField.fill(lenco.testMomoNumber || SEED.address.phone);
    }

    // 7. Initiate payment — the credential-free boundary: the app must move
    //    past the pay button into the honest USSD-wait/pending surface.
    await page
      .getByRole("button", { name: /pay|place order|checkout/i })
      .first()
      .click();
    await expect(page.getByTestId("ussd-wait").or(page.getByTestId("payment-cod"))).toBeVisible({
      timeout: 30_000,
    });

    // ── ENV-GATED: live Lenco sandbox charge → confirmation (F9b) ────────────
    if (!sandboxEnabled()) {
      test.info().annotations.push({
        type: "founder-gated",
        description:
          "Lenco sandbox pay skipped — set LENCO_SANDBOX=1 + LENCO_SANDBOX_* creds (F9b). Asserted browse→cart→pay-initiation only.",
      });
      test.skip(true, "Lenco sandbox pay leg is founder/staging-gated (F9b)");
      return;
    }

    // 8. Sandbox auto-approves the designated test MSISDN; the app confirms
    //    and lands on the order page — the real escrow/payment state surface
    //    (the customer app shows no bare "paid" screen by design, MR-C08).
    await page.waitForURL(/account\/orders/, { timeout: 90_000 });

    // 9. Order confirmation: an order surface with trust/escrow state renders.
    await expect(page.getByRole("heading").first()).toBeVisible();
    await expect(page.getByText(/order|escrow|held|delivery|pickup/i).first()).toBeVisible();
  });
});
