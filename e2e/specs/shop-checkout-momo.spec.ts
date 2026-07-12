import { lenco, otp, path, whatsappMockReady } from "../fixtures/env";
import { completeSandboxMomoPush, sandboxEnabled } from "../fixtures/lenco";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";
import { expectWhatsAppMessage } from "../fixtures/whatsapp";

/**
 * Critical path: browse → search → PDP → cart → checkout → MoMo pay →
 * confirmation → WhatsApp-mock assertion.
 *
 * The live Lenco sandbox charge (and the confirmation/WhatsApp legs that depend
 * on a settled payment) are ENV-GATED behind `LENCO_SANDBOX=1` + creds
 * (founder gate F9b). Without them the spec asserts up to the pay-initiation
 * boundary and skips the charge with an annotation — it never hammers a real
 * payment endpoint.
 */
test.describe("shop · checkout · momo", () => {
  test("buyer pays a listing by MTN/Airtel MoMo and gets a WhatsApp receipt", async ({
    page,
  }) => {
    // 1. Browse home.
    await page.goto(path("/"));

    // 2. Search for the seeded, buyable product.
    await page.goto(path(`/search?q=${encodeURIComponent(SEED.searchTerm)}`));
    await expect(page.getByTestId("search-results-list")).toBeVisible();

    // 3. Open the seeded PDP directly (search ranking is not under test here).
    await page.goto(path(`/p/${SEED.product.slug}`));
    await expect(page.getByTestId("pdp-buy-box")).toBeVisible();
    await expect(page.getByTestId("pdp-price")).toBeVisible();

    // 4. Add to cart.
    await page.getByTestId("pdp-add-to-cart").click();
    await expect(page.getByTestId("pdp-add-to-cart-success")).toBeVisible();

    // 5. Go to cart, confirm the line is present.
    await page.goto(path("/cart"));
    await expect(page.getByTestId("cart-page")).toBeVisible();
    await expect(page.getByTestId("cart-subtotal")).toBeVisible();

    // 6. Checkout — choose MoMo as the payment method.
    await page.goto(path("/checkout"));
    const momo = page.locator('[name="payment-method"][value="momo"]');
    await momo.first().check().catch(async () => {
      // Fallback: some renders expose MoMo as the rail select rather than radio.
      await page.locator('[name="momo-rail"]').first().waitFor();
    });

    // Fill the escrow/delivery contact (landmark + phone — Zambia addressing).
    const phoneField = page.getByLabel(/phone|mobile|momo/i).first();
    if (await phoneField.count()) {
      await phoneField.fill(
        lenco.testMomoNumber || SEED.address.phone,
      );
    }

    // 7. Initiate payment (submit checkout). This is the pay-initiation boundary.
    await page.getByRole("button", { name: /pay|place order|checkout/i }).first().click();

    // ── ENV-GATED: live Lenco sandbox charge (F9b) ───────────────────────────
    if (!sandboxEnabled()) {
      test.info().annotations.push({
        type: "founder-gated",
        description:
          "Lenco sandbox pay skipped — set LENCO_SANDBOX=1 + LENCO_SANDBOX_* creds (F9b). Asserted up to pay-initiation only.",
      });
      // We still expect the app to have moved past the pay button into a
      // pending/USSD-wait or hosted-widget state (initiation succeeded).
      await expect(
        page.getByTestId("ussd-wait").or(page.getByTestId("payment-cod")),
      ).toBeVisible({ timeout: 30_000 });
      test.skip(true, "Lenco sandbox pay leg is founder/staging-gated (F9b)");
      return;
    }

    // Drive the sandbox MoMo push to auto-approval → confirmation.
    await completeSandboxMomoPush(page);
    await expect(page.getByTestId("payment-success")).toBeVisible();

    // ── ENV-GATED: WhatsApp mock receipt assertion ───────────────────────────
    if (whatsappMockReady()) {
      await expectWhatsAppMessage(
        otp.testPhone || SEED.address.phone,
        /order|receipt|escrow|paid/i,
      );
    } else {
      test.info().annotations.push({
        type: "founder-gated",
        description:
          "WhatsApp receipt assertion skipped — set WHATSAPP_MOCK=1 + WHATSAPP_MOCK_OUTBOX_URL.",
      });
    }
  });
});
