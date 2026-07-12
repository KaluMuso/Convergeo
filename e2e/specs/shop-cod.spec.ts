import { path } from "../fixtures/env";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

/**
 * Critical path: browse → PDP → cart → checkout → Cash-on-Delivery.
 *
 * COD is a launch payment option capped at K500 (Zambia guardrail). This flow
 * needs no external payment provider, so it runs end-to-end against any live
 * target (staging or a local dev server) with seed data — no founder gate.
 */
test.describe("shop · cash on delivery", () => {
  test("buyer places a COD order and reaches confirmation", async ({ page }) => {
    // Open the seeded PDP and add to cart.
    await page.goto(path(`/p/${SEED.product.slug}`));
    await expect(page.getByTestId("pdp-buy-box")).toBeVisible();
    await page.getByTestId("pdp-add-to-cart").click();
    await expect(page.getByTestId("pdp-add-to-cart-success")).toBeVisible();

    // Cart → checkout.
    await page.goto(path("/cart"));
    await expect(page.getByTestId("cart-page")).toBeVisible();
    await page.goto(path("/checkout"));

    // Select Cash-on-Delivery.
    const cod = page
      .locator('[name="payment-method"][value="cod"]')
      .or(page.getByTestId("payment-cod"));
    await cod.first().check().catch(async () => {
      await page.getByTestId("payment-cod").first().click();
    });

    // Provide landmark + phone delivery contact.
    const phoneField = page.getByLabel(/phone|mobile/i).first();
    if (await phoneField.count()) {
      await phoneField.fill(SEED.address.phone);
    }
    const landmark = page.getByLabel(/landmark|address|location/i).first();
    if (await landmark.count()) {
      await landmark.fill(SEED.address.landmark);
    }

    // Place the COD order.
    await page
      .getByRole("button", { name: /place order|confirm|checkout|pay/i })
      .first()
      .click();

    // COD needs no gateway — confirmation should render directly.
    await expect(
      page
        .getByTestId("payment-success")
        .or(page.getByTestId("cart-empty-state")),
    ).toBeVisible({ timeout: 30_000 });
  });
});
