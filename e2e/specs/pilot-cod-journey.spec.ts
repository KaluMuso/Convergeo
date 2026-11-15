import { clickAddToCartAndAwaitOutcome } from "../fixtures/add-to-cart";
import { checkoutSurface, completeCheckout } from "../fixtures/checkout";
import { customerOtp, customerOtpReady, path } from "../fixtures/env";
import { resolveGate } from "../fixtures/gating";
import {
  guardApprovedOtpRequests,
  guardCodWithoutProvider,
  missingCodApproval,
} from "../fixtures/outbound-approval";
import { FORBIDDEN_SUCCESS_COPY } from "../fixtures/payment-fixtures";
import { expectNoRawI18n } from "../fixtures/raw-i18n";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

test.use({
  serviceWorkers: "block",
  viewport: { width: 360, height: 800 },
  trace: "off",
  video: "off",
  screenshot: "off",
});

/**
 * Pilot journeys 1 + 2 on the REAL stack: guest -> search -> PDP -> add to
 * cart -> sign in at checkout (OTP) -> Cash on Delivery -> confirmation ->
 * order tracking page.
 *
 * Gated exactly like shop-cod.spec.ts (approved customer OTP recipient, COD
 * without provider). Missing prerequisites skip with a founder-gated
 * annotation; shop-cod/auth-otp remain the REQUIRED_STRICT owners of that
 * fixture so one gap is not reported twice. The deterministic mock-mode
 * counterpart (cap handling, confirmation copy) is pilot-cod-checkout.spec.ts.
 */
test.describe("pilot · guest to COD to tracking (real stack)", () => {
  test.describe.configure({ retries: 0 });

  test("guest buys on COD and can track the placed order", async ({ page }) => {
    if (!customerOtpReady()) {
      const gate = resolveGate({
        kind: "OPTIONAL_GATE",
        journey: "pilot guest-to-COD-to-tracking (authenticated buyer)",
        fixtures: [
          "E2E_CUSTOMER_TEST_OTP",
          "SMS_OTP_TRANSPORT",
          "WAHA_OTP_ENABLED",
          "STAGING_SMS_SANDBOX_ATTESTED",
          "STAGING_TEST_OTP_MAP_ATTESTED",
        ],
      });
      test.info().annotations.push({ type: "founder-gated", description: gate.reason });
      test.skip(true, gate.reason);
      return;
    }
    const missingApproval = missingCodApproval(customerOtp.testPhone);
    if (missingApproval.length) {
      const gate = resolveGate({
        kind: "OPTIONAL_GATE",
        journey: "approved customer OTP for pilot COD journey",
        fixtures: missingApproval,
      });
      test.info().annotations.push({ type: "founder-gated", description: gate.reason });
      test.skip(true, gate.reason);
      return;
    }
    await guardApprovedOtpRequests(page, "customer", customerOtp.testPhone);
    await guardCodWithoutProvider(page, customerOtp.testPhone);

    // Guest: search finds the seeded product and its card opens the PDP.
    await page.goto(path(`/search?q=${encodeURIComponent(SEED.searchTerm)}`));
    const productLink = page.locator(`a[href*="/p/${SEED.product.slug}"]`).first();
    await expect(productLink).toBeVisible({ timeout: 30_000 });
    await productLink.click();
    await expect(page).toHaveURL(new RegExp(`/p/${SEED.product.slug}`));
    await expect(page.getByTestId("pdp-buy-box")).toBeVisible();
    await expectNoRawI18n(page, "main");

    await clickAddToCartAndAwaitOutcome(page, test.info(), { timeout: 15_000 });
    await page.goto(path("/cart"));
    await expect(page.getByTestId("cart-vendor-groups")).toBeVisible({ timeout: 20_000 });

    // Sign-in happens inside checkout (Contact step OTP) via the shared driver.
    await page.goto(path("/checkout"));
    await expect(checkoutSurface(page)).toBeVisible({ timeout: 30_000 });
    await completeCheckout(page, { payment: "cod" });

    // Confirmation: pay-on-delivery next steps, never a paid claim.
    const cod = page.getByTestId("payment-cod");
    await expect(cod).toBeVisible({ timeout: 30_000 });
    await expect(cod.getByRole("heading")).toContainText(/pay on delivery/i);
    await expect(page.getByText(FORBIDDEN_SUCCESS_COPY)).toHaveCount(0);
    await expectNoRawI18n(page, "main");

    // Tracking: the order page renders a status timeline with COD copy.
    await cod.getByRole("link").click();
    await expect(page).toHaveURL(/\/account\/orders\/[0-9a-f-]{36}$/i, { timeout: 30_000 });
    await expect(page.getByRole("heading", { name: /^order [0-9A-F]{8}$/ })).toBeVisible();
    const timeline = page.locator("section[aria-labelledby='order-timeline-heading']");
    await expect(timeline).toBeVisible();
    await expect(timeline.getByRole("heading", { name: /order progress/i })).toBeVisible();
    await expect(timeline.locator("ol > li").first()).toContainText(/order placed/i);
    await expect(timeline).toContainText(/pay the vendor on delivery/i);
    await expect(timeline).toContainText(/pay the vendor in cash or mobile money/i);
    // COD must not show the prepaid escrow-held promise.
    await expect(timeline).not.toContainText(/you paid|held safely/i);
    await expectNoRawI18n(page);
  });
});
