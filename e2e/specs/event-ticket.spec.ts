import {
  otpVerifyReady,
  path,
  urlOn,
  VENDOR_BASE_URL,
} from "../fixtures/env";
import { sandboxEnabled } from "../fixtures/lenco";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

/**
 * Critical path: buy an event ticket → see it in the wallet → organiser scanner
 * verifies it → a second scan of the same ticket is rejected (dynamic-QR,
 * single-use).
 *
 * Legs and their gates:
 *  - Ticket PURCHASE is a Lenco charge → gated behind `LENCO_SANDBOX` (F9b).
 *  - Scanner VERIFY / duplicate-reject runs on the vendor app (separate origin)
 *    and needs an organiser session → gated behind OTP test creds. A seeded
 *    single-use ticket token may be supplied via `E2E_TICKET_QR` so the
 *    duplicate-reject assertion can run without a live purchase.
 */
test.describe("event · ticket lifecycle", () => {
  test("buy → wallet → scan verify → duplicate rejected", async ({ page }) => {
    // Event PDP.
    await page.goto(path(`/e/${SEED.event.slug}`));

    // ── Purchase leg (Lenco-gated) ───────────────────────────────────────────
    if (sandboxEnabled()) {
      const buy = page.getByRole("button", { name: /buy|get ticket|book/i }).first();
      await expect(buy).toBeVisible();
      await buy.click();
      // Purchase drives the shared checkout → confirmation.
      await expect(page.getByTestId("payment-success")).toBeVisible({
        timeout: 90_000,
      });
      // Wallet shows the purchased ticket.
      await page.goto(path("/account/tickets"));
      await expect(
        page.getByRole("heading", { name: /ticket/i }).first(),
      ).toBeVisible();
    } else {
      test.info().annotations.push({
        type: "founder-gated",
        description:
          "Ticket purchase + wallet skipped — needs LENCO_SANDBOX (F9b). Asserted event PDP renders only.",
      });
      await expect(page).toHaveURL(new RegExp(`/e/${SEED.event.slug}`));
    }

    // ── Scanner verify + duplicate-reject leg (vendor app, OTP-gated) ─────────
    const ticketQr = process.env.E2E_TICKET_QR?.trim();
    if (!otpVerifyReady() || !ticketQr) {
      test.info().annotations.push({
        type: "founder-gated",
        description:
          "Scanner verify/duplicate-reject skipped — needs vendor OTP creds + E2E_TICKET_QR (staging). Asserting scanner surface loads.",
      });
      await page.goto(urlOn(VENDOR_BASE_URL, `/events/${SEED.event.slug}/scan`));
      await expect(
        page
          .getByTestId("scan-pin-fallback")
          .or(page.getByTestId("scan-camera-loading"))
          .or(page.getByTestId("event-scan-count")),
      ).toBeVisible();
      test.skip(true, "Ticket scan flow is staging/founder-gated (F9b + organiser OTP)");
      return;
    }

    // Organiser scanner — use the PIN/manual fallback to submit a ticket token.
    await page.goto(urlOn(VENDOR_BASE_URL, `/events/${SEED.event.slug}/scan`));
    await page.getByTestId("scan-switch-pin").click().catch(() => {});
    const pinInput = page.getByTestId("scan-pin-fallback").getByRole("textbox");

    // First scan → verified.
    await pinInput.fill(ticketQr);
    await page.getByRole("button", { name: /verify|check|scan/i }).first().click();
    await expect(page.getByTestId("scan-success")).toBeVisible({ timeout: 20_000 });

    // Second scan of the same ticket → duplicate rejected (not a success).
    await pinInput.fill(ticketQr);
    await page.getByRole("button", { name: /verify|check|scan/i }).first().click();
    await expect(
      page.getByText(/already|duplicate|used|rejected/i).first(),
    ).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("scan-success")).toBeHidden();
  });
});
