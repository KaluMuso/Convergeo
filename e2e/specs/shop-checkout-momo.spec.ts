import { clickAddToCartAndAwaitOutcome } from "../fixtures/add-to-cart";
import { checkoutSurface, completeCheckout } from "../fixtures/checkout";
import { customerOtp, customerOtpReady, lenco, path, whatsappMockReady } from "../fixtures/env";
import { resolveGate } from "../fixtures/gating";
import { completeSandboxMomoPush, sandboxEnabled } from "../fixtures/lenco";
import { captureSearchStateOnFailure } from "../fixtures/search-diagnostics";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";
import { expectWhatsAppMessage } from "../fixtures/whatsapp";

/**
 * Critical path: browse → PDP → cart → the REAL four-step checkout → MoMo pay
 * → confirmation → WhatsApp-mock assertion.
 *
 * Same S2 defect as shop-cod: the spec reached /checkout and immediately went
 * for `[name="payment-method"][value="momo"]` and a pay button while the app
 * was still on "Step 1 of 4 · Your contact details". The wizard is now driven
 * for real through `fixtures/checkout.ts`:
 * Contact → Fulfilment → Payment (MoMo rail + payer number) → Review → Place
 * order, and only then is the Lenco sandbox leg considered.
 *
 * SEARCH: this spec's own doc comment has always said search ranking is not
 * its subject, so search is no longer a prerequisite for the commerce journey.
 * It stays as a DIAGNOSTIC leg — recorded, never gating — and the PDP is
 * opened canonically by seeded slug. Independent browse/search coverage is
 * unchanged and still enforced in critical-path.spec.ts and
 * browse-journey.spec.ts.
 *
 * The live Lenco sandbox charge (and the confirmation/WhatsApp legs that
 * depend on a settled payment) remain ENV-GATED behind `LENCO_SANDBOX` + creds
 * (founder gate F9b). Without them the spec asserts up to the real
 * pay-initiation boundary — which is now an actually-placed order sitting on
 * the USSD wait — and skips the charge with an annotation.
 */
test.describe("shop · checkout · momo", () => {
  test("buyer pays a listing by MTN/Airtel MoMo and gets a WhatsApp receipt", async ({ page }) => {
    // Checkout is authenticated. As in shop-cod, the identical fixture is
    // already REQUIRED_STRICT at auth-otp.spec.ts, so certification coverage
    // cannot be lost silently by classifying it OPTIONAL_GATE here.
    if (!customerOtpReady()) {
      const gate = resolveGate({
        kind: "OPTIONAL_GATE",
        journey: "MoMo checkout placement (authenticated buyer)",
        fixtures: ["E2E_CUSTOMER_TEST_OTP"],
      });
      test.info().annotations.push({ type: "founder-gated", description: gate.reason });
      test.skip(true, gate.reason);
      return;
    }

    // 1. Browse home.
    await page.goto(path("/"));

    // 2. Search — DIAGNOSTIC ONLY on this spec (see the note above). A zero-hit
    //    or unavailable search surface is recorded and the commerce journey
    //    continues; it is browse-journey/critical-path that own search as a
    //    gating assertion.
    await page.goto(path(`/search?q=${encodeURIComponent(SEED.searchTerm)}`));
    const searchReady = await captureSearchStateOnFailure(page, () =>
      page
        .getByTestId("search-results-list")
        .waitFor({ state: "visible", timeout: 15_000 })
        .then(() => true),
    ).catch(() => false);
    test.info().annotations.push({
      type: "search-diagnostic",
      description: `search-results-list visible for "${SEED.searchTerm}": ${searchReady}`,
    });

    // 3. Open the canonical seeded PDP directly — the actual subject of this spec.
    await page.goto(path(`/p/${SEED.product.slug}`));
    await expect(page.getByTestId("pdp-buy-box")).toBeVisible();
    await expect(page.getByTestId("pdp-price")).toBeVisible();

    // 4. Add to cart.
    await clickAddToCartAndAwaitOutcome(page, test.info(), { timeout: 15_000 });

    // 5. Go to cart, confirm the line is present.
    await page.goto(path("/cart"));
    await expect(page.getByTestId("cart-page")).toBeVisible();
    await expect(page.getByTestId("cart-subtotal")).toBeVisible();

    // 6. The real four-step checkout, paying by MoMo.
    await page.goto(path("/checkout"));
    await expect(checkoutSurface(page)).toBeVisible({ timeout: 30_000 });

    const run = await completeCheckout(page, {
      payment: "momo",
      rail: "mtn",
      // The sandbox MSISDN Lenco auto-approves when the F9b gate is open;
      // otherwise the canonical synthetic buyer number. Both are normalised to
      // the 9-digit national form the payer field accepts.
      payerPhone: lenco.testMomoNumber || SEED.address.phone,
    });
    expect(run.payment).toBe("momo");
    expect(run.payerNationalNumber).not.toBeNull();
    test.info().annotations.push({
      type: "checkout",
      description: `contact=${run.contact}; fulfilment=${run.fulfilment.join(",")}`,
    });

    // 7. Pay-initiation boundary — a REAL placed order awaiting USSD approval.
    await expect(
      page.getByTestId("ussd-wait").or(page.getByTestId("payment-confirming")).first(),
    ).toBeVisible({ timeout: 30_000 });
    // MoMo is not COD: the COD surface must never appear on this journey.
    await expect(page.getByTestId("payment-cod")).toHaveCount(0);

    // ── ENV-GATED: live Lenco sandbox charge (F9b) ───────────────────────────
    if (!sandboxEnabled()) {
      const gate = resolveGate({
        kind: "OPTIONAL_GATE",
        journey: "Lenco sandbox charge (F9b)",
        fixtures: ["LENCO_SANDBOX"],
      });
      test.info().annotations.push({ type: "founder-gated", description: gate.reason });
      test.skip(true, gate.reason);
      return;
    }

    // Drive the sandbox MoMo push to auto-approval → confirming surface
    // (payment-outcome honesty: never infer a local payment-success).
    await completeSandboxMomoPush(page);
    await expect(
      page.getByTestId("payment-confirming").or(page.getByTestId("ussd-wait")),
    ).toBeVisible();

    // ── ENV-GATED: WhatsApp mock receipt assertion ───────────────────────────
    if (whatsappMockReady()) {
      await expectWhatsAppMessage(
        customerOtp.testPhone || SEED.address.phone,
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
