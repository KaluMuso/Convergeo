import {
  checkoutShell,
  checkoutSurface,
  completeFulfilmentStep,
  completePaymentStep,
  waitForCheckoutStep,
} from "../fixtures/checkout";
import { COD_CAP_NGWEE, installMockCheckoutApi } from "../fixtures/checkout-api-mock";
import { path } from "../fixtures/env";
import {
  FIXTURE_GROUP_ID,
  FIXTURE_ORDER_ID,
  FORBIDDEN_SUCCESS_COPY,
  assertNoAccidentalRealMoney,
  installMockBuyerSession,
  mockPaymentStatus,
  statusFixture,
} from "../fixtures/payment-fixtures";
import { expectNoRawI18n } from "../fixtures/raw-i18n";
import { expect, test } from "../fixtures/test-base";

// Customer pilot viewport (CLAUDE.md: 360px-first) regardless of the project's.
test.use({ serviceWorkers: "block", viewport: { width: 360, height: 800 } });

/**
 * Pilot journey 1 (mock mode): checkout -> Cash on Delivery.
 *
 * Runs with no backend and no OTP: the wizard's API is answered by
 * fixtures/checkout-api-mock.ts and the buyer session by
 * installMockBuyerSession, exactly like checkout-false-success. The real-stack
 * variant (guest -> search -> PDP -> cart -> OTP -> COD -> tracking) lives in
 * pilot-cod-journey.spec.ts and is founder/OTP gated.
 */
test.describe("pilot · COD checkout (mock API)", () => {
  test.beforeEach(() => assertNoAccidentalRealMoney());

  test("COD under the K500 cap: next-steps copy, then an honest pay-on-delivery confirmation", async ({
    page,
  }) => {
    await installMockBuyerSession(page);
    const calls = await installMockCheckoutApi(page, {
      subtotalNgwee: 25_000,
      deliveryFeeNgwee: 2_000,
    });
    await mockPaymentStatus(
      page,
      statusFixture({ status: "cod", cod: true, payment_id: null, amount_ngwee: 27_000 }),
    );

    await page.goto(path("/checkout"));
    await expect(checkoutSurface(page)).toBeVisible();

    const fulfilment = await completeFulfilmentStep(page);
    expect(fulfilment).toEqual(["delivery"]);
    await completePaymentStep(page, { payment: "cod" });

    // Review: the buyer is told what happens next before committing.
    await waitForCheckoutStep(page, "review");
    const shell = checkoutShell(page);
    await expect(shell.getByText(/what happens next/i)).toBeVisible();
    await expect(shell.getByText(/pay the courier when the order arrives/i)).toBeVisible();
    await expect(shell.getByText(/cash on delivery/i).first()).toBeVisible();

    await page.locator("#checkout-consent").check();
    await page.getByTestId("checkout-place-order").click();

    // Terminal surface: order placed, pay on delivery, with the amount.
    const cod = page.getByTestId("payment-cod");
    await expect(cod).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/checkout/pending/${FIXTURE_GROUP_ID}$`));
    await expect(
      cod.getByRole("heading", { name: /order placed.*pay on delivery/i }),
    ).toBeVisible();
    await expect(cod).toContainText("K270.00");
    await expect(cod.getByRole("link", { name: /view order details/i })).toHaveAttribute(
      "href",
      new RegExp(`/account/orders/${FIXTURE_ORDER_ID}$`),
    );
    await expect(page.getByTestId("payment-confirming")).toHaveCount(0);
    await expect(page.getByTestId("ussd-wait")).toHaveCount(0);
    await expect(page.getByText(FORBIDDEN_SUCCESS_COPY)).toHaveCount(0);
    await expect(page.getByText(/you paid|held by convergeo/i)).toHaveCount(0);
    await expectNoRawI18n(page, "main");

    expect(calls.orders).toHaveLength(1);
    expect(calls.orders[0]).toMatchObject({ method: "cod", session_id: FIXTURE_GROUP_ID });
  });

  test("COD above the K500 cap is explained and not offered", async ({ page }) => {
    await installMockBuyerSession(page);
    const calls = await installMockCheckoutApi(page, { subtotalNgwee: 62_500 });
    expect(62_500).toBeGreaterThan(COD_CAP_NGWEE);

    await page.goto(path("/checkout"));
    await expect(checkoutSurface(page)).toBeVisible();
    await completeFulfilmentStep(page);

    const methods = page.getByTestId("checkout-payment-methods");
    await expect(methods).toBeVisible();

    const unavailable = page.getByTestId("checkout-cod-unavailable");
    await expect(unavailable).toBeVisible();
    await expect(unavailable).toContainText(/cash on delivery unavailable/i);
    // Only mobile money + card are selectable; COD is not a radio.
    await expect(methods.locator('input[name="payment-method"]')).toHaveCount(2);

    // The wizard cannot be advanced into a COD order.
    expect(calls.orders).toHaveLength(0);
    expect(calls.paymentSteps).toHaveLength(0);
  });

  test.fixme("COD-cap explanation states the K500 cap, not a raw message id", async ({ page }) => {
    // BUG (found by this suite): apps/customer/app/[locale]/(shop)/checkout/page.tsx:140
    // builds `codIneligibleTemplate` with t("checkout.payment.codIneligible"),
    // but the message has a {cap} argument. t() without the argument throws a
    // formatting error and next-intl returns the id, so the buyer sees
    // "checkout.checkout.payment.codIneligible" instead of "Cash on delivery is
    // only available for orders up to K500.00". The sibling labels use
    // t.raw(...) (e.g. line 40); this one should too. Remove fixme once fixed.
    await installMockBuyerSession(page);
    await installMockCheckoutApi(page, { subtotalNgwee: 62_500 });
    await page.goto(path("/checkout"));
    await completeFulfilmentStep(page);
    const unavailable = page.getByTestId("checkout-cod-unavailable");
    await expect(unavailable).toContainText("K500.00");
    await expectNoRawI18n(page, "main");
  });

  test.fixme("COD confirmation shows the order number", async ({ page }) => {
    // FINDING: the COD confirmation (checkout/pending -> payment-cod in
    // ussd-wait.tsx) renders only codTitle, codBody{amount} and a CTA. The
    // customer-facing order number ("Order ABCD1234", orders.detail.orderId)
    // appears only after tapping through to /account/orders/{id}. Pilot
    // expectation: confirmation shows the order number. Remove fixme when the
    // pending page renders it.
    await installMockBuyerSession(page);
    await mockPaymentStatus(
      page,
      statusFixture({ status: "cod", cod: true, payment_id: null, amount_ngwee: 27_000 }),
    );
    await page.goto(path(`/checkout/pending/${FIXTURE_GROUP_ID}`));
    await expect(page.getByTestId("payment-cod")).toContainText(
      FIXTURE_ORDER_ID.slice(0, 8).toUpperCase(),
    );
  });
});
