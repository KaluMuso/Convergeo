import type { Page } from "@playwright/test";

import { path } from "../fixtures/env";
import { sandboxEnabled } from "../fixtures/lenco";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

/**
 * VB-P07 · MR-C08 / S6 / G4 — a pending or failed MoMo payment must NEVER
 * render as "paid", and a COD order must never claim a MoMo/prepaid success.
 * (Happy path lives in critical-path.spec.ts — VE-P07, distinct file.)
 *
 * The customer checkout is designed with NO bare "paid" screen: MoMo success
 * only redirects to the order page (real escrow state), card success requires
 * `order_confirmed`, and the transitional `payment-confirming` copy explicitly
 * says it is not a final paid confirmation. These specs prove the UI holds
 * that line on the three risk paths:
 *  (a) MoMo initiated but never approved → stays on the honest waiting surface;
 *  (b) failed/declined MoMo → failure UI + retry, never success;
 *  (c) COD (≤ K500 cap) → pay-on-delivery copy, never a prepaid-success claim.
 *
 * The pending and COD assertions run CREDENTIAL-FREE against any live target.
 * Only the forced-decline leg is ENV-GATED (`LENCO_SANDBOX` creds — founder
 * gate F9b — plus a Lenco declining MSISDN via `E2E_MOMO_DECLINE_NUMBER`);
 * absent env it skips with an annotation, existing `e2e/` pattern.
 */

/**
 * Copy that would claim a settled payment. "Order confirmed" is the card
 * success title — legal only after ledger-confirmed `order_confirmed`, so it
 * must never appear on a pending/failed MoMo or COD surface. The customer app
 * defines no `payment-success` testid at all; one appearing is a regression.
 */
const SUCCESS_CLAIM = /order confirmed|payment successful|payment received|payment complete/i;

/** Placeholder group id (matches the pending route's static-params fixture). */
const UNKNOWN_GROUP_ID = "00000000-0000-0000-0000-000000000000";

/** Assert the page is not claiming a paid/success state anywhere. */
async function expectNoSuccessClaim(page: Page): Promise<void> {
  await expect(page.getByTestId("payment-success")).toHaveCount(0);
  await expect(page.getByText(SUCCESS_CLAIM)).toHaveCount(0);
}

/** PDP → add to cart → cart (seeded buyable product). */
async function addSeedProductToCart(page: Page): Promise<void> {
  await page.goto(path(`/p/${SEED.product.slug}`));
  await expect(page.getByTestId("pdp-buy-box")).toBeVisible();
  await page.getByTestId("pdp-add-to-cart").click();
  await expect(page.getByTestId("pdp-add-to-cart-success")).toBeVisible();
  await page.goto(path("/cart"));
  await expect(page.getByTestId("cart-page")).toBeVisible();
}

test.describe("checkout · false-success (S6/G4)", () => {
  test("MoMo initiated but never approved stays pending — never renders paid", async ({ page }) => {
    await addSeedProductToCart(page);
    await page.goto(path("/checkout"));

    // Choose MoMo (radio; fallback to the rail-select render).
    const momo = page.locator('[name="payment-method"][value="momo"]');
    await momo
      .first()
      .check()
      .catch(async () => {
        await page.locator('[name="momo-rail"]').first().waitFor();
      });

    // Deliberately use the seed phone — NOT the Lenco sandbox auto-approve
    // number — so the USSD push is never approved and the payment stays pending.
    const phoneField = page.getByLabel(/phone|mobile|momo/i).first();
    if (await phoneField.count()) {
      await phoneField.fill(SEED.address.phone);
    }

    // Initiate payment.
    await page
      .getByRole("button", { name: /pay|place order|checkout/i })
      .first()
      .click();

    // Pay-initiation boundary: only a truthful surface may render — the USSD
    // waiting card, a failure card, or the checkout error. Never success.
    await expect(
      page
        .getByTestId("ussd-wait")
        .or(page.getByTestId("payment-failed"))
        .or(page.getByTestId("checkout-payment-error")),
    ).toBeVisible({ timeout: 30_000 });
    await expectNoSuccessClaim(page);

    // Observe ~3 status-poll cycles (2s→4s→8s backoff): with no approval the
    // page must never enter `payment-confirming` (only legal after a provider
    // success signal), never redirect to the order page, never show paid copy.
    for (let cycle = 0; cycle < 3; cycle += 1) {
      await page.waitForTimeout(4_000);
      await expect(page).not.toHaveURL(/account\/orders/);
      await expect(page.getByTestId("payment-confirming")).toHaveCount(0);
      await expectNoSuccessClaim(page);
    }

    // While waiting, the USSD surface must carry honest waiting copy.
    const ussd = page.getByTestId("ussd-wait");
    if (await ussd.isVisible().catch(() => false)) {
      await expect(ussd.getByText(/waiting for approval/i)).toBeVisible();
    }
  });

  test("failed/declined MoMo shows the failure surface with retry — never paid", async ({
    page,
  }) => {
    // CREDENTIAL-FREE boundary: the pending status page for an unknown checkout
    // group renders the honest "Approve payment" shell (loading/error only) —
    // it can never claim success without a confirmed payment behind it.
    await page.goto(path(`/checkout/pending/${UNKNOWN_GROUP_ID}`));
    await expect(
      page.getByRole("heading", { name: /approve payment/i }).or(page.locator("h1").first()),
    ).toBeVisible();
    await expect(page.getByTestId("payment-confirming")).toHaveCount(0);
    await expect(page.getByTestId("payment-cod")).toHaveCount(0);
    await expectNoSuccessClaim(page);

    // ── ENV-GATED: forced sandbox decline (F9b + declining MSISDN) ───────────
    const declineNumber = process.env.E2E_MOMO_DECLINE_NUMBER?.trim();
    if (!sandboxEnabled() || !declineNumber) {
      test.info().annotations.push({
        type: "founder-gated",
        description:
          "Forced MoMo decline skipped — needs LENCO_SANDBOX creds (F9b) + E2E_MOMO_DECLINE_NUMBER (a Lenco sandbox declining MSISDN). Asserted the pending shell never claims success.",
      });
      test.skip(true, "Forced-decline leg is founder/staging-gated (F9b)");
      return;
    }

    await addSeedProductToCart(page);
    await page.goto(path("/checkout"));
    const momo = page.locator('[name="payment-method"][value="momo"]');
    await momo
      .first()
      .check()
      .catch(async () => {
        await page.locator('[name="momo-rail"]').first().waitFor();
      });
    const phoneField = page.getByLabel(/phone|mobile|momo/i).first();
    if (await phoneField.count()) {
      await phoneField.fill(declineNumber);
    }
    await page
      .getByRole("button", { name: /pay|place order|checkout/i })
      .first()
      .click();
    await expect(page.getByTestId("ussd-wait")).toBeVisible({ timeout: 30_000 });

    // The declined/failed push must land on a failure surface with a retry
    // path — and never a success claim.
    const failure = page
      .getByTestId("payment-failed")
      .or(page.getByTestId("payment-cancelled"))
      .or(page.getByTestId("payment-expired"));
    await expect(failure.first()).toBeVisible({ timeout: 60_000 });
    await expect(
      page
        .getByTestId("payment-retry-button")
        .or(page.getByRole("button", { name: /retry|back to checkout/i })),
    ).toBeVisible();
    await expect(page.getByTestId("ussd-wait")).toBeHidden();
    await expect(page.getByTestId("payment-confirming")).toHaveCount(0);
    await expectNoSuccessClaim(page);
  });

  test("COD order (≤ K500 cap) shows pay-on-delivery copy — never MoMo/prepaid success", async ({
    page,
  }) => {
    await addSeedProductToCart(page);
    await page.goto(path("/checkout"));

    // Select Cash-on-Delivery (only offered under the K500 cap — guardrail).
    const cod = page
      .locator('[name="payment-method"][value="cod"]')
      .or(page.getByTestId("payment-cod"));
    await cod
      .first()
      .check()
      .catch(async () => {
        await page.getByTestId("payment-cod").first().click();
      });

    // Landmark + phone delivery contact (Zambia addressing).
    const phoneField = page.getByLabel(/phone|mobile/i).first();
    if (await phoneField.count()) {
      await phoneField.fill(SEED.address.phone);
    }
    const landmark = page.getByLabel(/landmark|address|location/i).first();
    if (await landmark.count()) {
      await landmark.fill(SEED.address.landmark);
    }

    // Place the COD order — no payment gateway involved.
    await page
      .getByRole("button", { name: /place order|confirm|checkout|pay/i })
      .first()
      .click();

    // COD confirmation surface (or emptied cart) renders directly.
    await expect(
      page.getByTestId("payment-cod").or(page.getByTestId("cart-empty-state")),
    ).toBeVisible({ timeout: 30_000 });

    // A COD order must never claim a prepaid/MoMo success: no USSD waiting, no
    // confirming state, no paid copy — COD collects cash at the door.
    await expect(page.getByTestId("ussd-wait")).toHaveCount(0);
    await expect(page.getByTestId("payment-confirming")).toHaveCount(0);
    await expectNoSuccessClaim(page);

    // When the COD confirmation rendered, it must carry collect-at-delivery
    // wording (codTitle/codBody), not prepaid escrow-released messaging.
    const codConfirm = page.getByTestId("payment-cod");
    if (await codConfirm.isVisible().catch(() => false)) {
      await expect(codConfirm.getByText(/pay on delivery|cash/i).first()).toBeVisible();
    }
  });
});
