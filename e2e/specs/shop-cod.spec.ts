import { clickAddToCartAndAwaitOutcome } from "../fixtures/add-to-cart";
import { checkoutSurface, completeCheckout } from "../fixtures/checkout";
import { customerOtpReady, path } from "../fixtures/env";
import { resolveGate } from "../fixtures/gating";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

/**
 * Critical path: browse → PDP → cart → the REAL four-step checkout →
 * Cash-on-Delivery placement.
 *
 * S2's staging run proved this spec was never placing an order. It landed on
 * /checkout and went straight for `[name="payment-method"][value="cod"]` and a
 * `/place order|confirm|checkout|pay/i` button, while the deployed app was
 * still on
 *
 *   Checkout
 *   Step 1 of 4
 *   Your contact details
 *
 * Two defects, not one: the wizard was never advanced past Contact, and the
 * COD radio has no `value` attribute at all (StepPayment renders
 * `<Radio name="payment-method">` with a label, no value), so that selector
 * could not have matched even on the Payment step. The terminal assertion then
 * accepted `cart-empty-state`, which an abandoned cart also produces — so the
 * spec could report green having bought nothing.
 *
 * It now drives Contact → Fulfilment → Payment → Review → Place order through
 * `fixtures/checkout.ts`, against the real deployed UI and the real API, and
 * asserts the one honest COD terminal state.
 *
 * COD needs no payment provider, so there is still no Lenco gate. It DOES need
 * a Customer session, because `POST /checkout/session` is authenticated — that
 * is the app's contract, not a test convenience.
 */
test.describe("shop · cash on delivery", () => {
  test("buyer places a COD order and reaches confirmation", async ({ page }) => {
    const checkoutFailures: string[] = [];
    page.on("response", (response) => {
      if (response.status() < 400 || !response.url().includes("/checkout/steps/fulfilment")) return;
      void response.json().then((body: unknown) => {
        const record = body && typeof body === "object" ? body as Record<string, unknown> : {};
        const error = record.error && typeof record.error === "object"
          ? record.error as Record<string, unknown> : record;
        checkoutFailures.push(`${response.status()}:${String(error.code ?? "unknown")}`);
      }).catch(() => checkoutFailures.push(`${response.status()}:unreadable`));
    });
    // Checkout is authenticated. The same fixture is already REQUIRED_STRICT at
    // auth-otp.spec.ts, so a certification run cannot silently lose customer-OTP
    // coverage; escalating the identical missing fixture a second time here
    // would report one gap twice. Outside a certification run this stays an
    // honest, annotated skip.
    if (!customerOtpReady()) {
      const gate = resolveGate({
        kind: "OPTIONAL_GATE",
        journey: "COD checkout placement (authenticated buyer)",
        fixtures: ["E2E_CUSTOMER_TEST_OTP"],
      });
      test.info().annotations.push({ type: "founder-gated", description: gate.reason });
      test.skip(true, gate.reason);
      return;
    }

    // Open the seeded PDP and add to cart.
    await page.goto(path(`/p/${SEED.product.slug}`));
    await expect(page.getByTestId("pdp-buy-box")).toBeVisible();
    await clickAddToCartAndAwaitOutcome(page, test.info(), { timeout: 15_000 });

    // Cart → checkout.
    await page.goto(path("/cart"));
    await expect(page.getByTestId("cart-page")).toBeVisible();
    await page.goto(path("/checkout"));

    // The Checkout surface itself — the Stepper, which only Checkout renders.
    await expect(checkoutSurface(page)).toBeVisible({ timeout: 30_000 });

    // The real wizard, end to end.
    const run = await completeCheckout(page, { payment: "cod" }).catch((error: unknown) => {
      throw new Error(`COD checkout failed; fulfilment API=${checkoutFailures.join(",")}; ${String(error)}`);
    });
    expect(run.payment).toBe("cod");
    expect(run.fulfilment.length).toBeGreaterThan(0);
    test.info().annotations.push({
      type: "checkout",
      description: `contact=${run.contact}; fulfilment=${run.fulfilment.join(",")}`,
    });

    // COD needs no gateway: the honest terminal state is "order placed, pay the
    // courier" — never a local payment-success claim (payment-outcome honesty),
    // and never an empty cart, which an abandoned checkout also produces.
    await expect(page.getByTestId("payment-cod")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("payment-confirming")).toHaveCount(0);
    await expect(page.getByTestId("ussd-wait")).toHaveCount(0);
  });
});
