import { expect } from "@playwright/test";

import type { Page, TestInfo } from "@playwright/test";

/**
 * Click "Add to cart" and wait for the honest success/error outcome the PDP
 * itself renders (pdp-add-to-cart-success / pdp-add-to-cart-error), then
 * annotate the run with the outcome plus the /cart/items response status
 * when one was observed — a CORS-blocked preflight (RC-6) never sends the
 * real request, so "no-response" is itself diagnostic. Never logs cookies,
 * Authorization, tokens, or response bodies — a numeric status only.
 *
 * This is a diagnostic aid, not a gate change: a failed add-to-cart still
 * throws exactly as before, just with the outcome/status attached to the
 * failure for faster triage.
 *
 * A branch-tracked listing requires an explicit pickup branch before Add to
 * Cart is even enabled (cart.pickup_location_required). This drives the
 * REAL UI: it waits (bounded, briefly) for the picker to appear and, only
 * if it does, selects the first real option through the select element —
 * it never injects pickup_location_id directly into API traffic, since
 * that would test a different, API-level contract instead of the actual
 * Customer journey. A legacy (non-branch-tracked) listing never renders
 * the picker at all, so this is a no-op for it.
 */
export async function clickAddToCartAndAwaitOutcome(
  page: Page,
  testInfo: TestInfo,
  options: { timeout?: number } = {},
): Promise<void> {
  const timeout = options.timeout ?? 15_000;

  const pickupSelect = page.getByTestId("pdp-pickup-location-select");
  const pickupRequired = await pickupSelect
    .waitFor({ state: "visible", timeout: 5_000 })
    .then(() => true)
    .catch(() => false);
  if (pickupRequired) {
    const branchOptions = await pickupSelect.locator("option:not([value=''])").allTextContents();
    if (branchOptions.length === 0) {
      throw new Error(
        "pdp-pickup-location-select rendered with no selectable branch — cannot proceed",
      );
    }
    await pickupSelect.selectOption({ index: 1 });
  }

  const cartItemsResponse = page
    .waitForResponse(
      (res) => res.request().method() === "POST" && res.url().includes("/cart/items"),
      { timeout },
    )
    .catch(() => null);

  await page.getByTestId("pdp-add-to-cart").click();

  const outcome = page
    .getByTestId("pdp-add-to-cart-success")
    .or(page.getByTestId("pdp-add-to-cart-error"));
  await expect(outcome.first()).toBeVisible({ timeout });

  const response = await cartItemsResponse;
  const succeeded = await page
    .getByTestId("pdp-add-to-cart-success")
    .isVisible()
    .catch(() => false);
  const status = response ? String(response.status()) : "no-response";

  testInfo.annotations.push({
    type: succeeded ? "pdp-add-to-cart-success" : "pdp-add-to-cart-error",
    description: `cart/items status=${status}`,
  });

  if (!succeeded) {
    throw new Error(`pdp-add-to-cart-error: add to cart failed (cart/items status=${status})`);
  }
}
