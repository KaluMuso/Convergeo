import { path, requireVendorBaseUrl, ticketPin, urlOn, vendorOtpReady } from "../fixtures/env";
import { enforceGate, resolveGate } from "../fixtures/gating";
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
 *    run-scoped single-use ticket PIN is supplied via `E2E_TICKET_PIN` so the
 *    duplicate-reject assertion can run without a live purchase.
 */
test.describe("event · ticket lifecycle", () => {
  test("buy → wallet → scan verify → duplicate rejected", async ({ page }) => {
    // The scanner legs below navigate the vendor origin directly; in a strict
    // certification run an unset/collapsed vendor target fails here rather
    // than silently scanning on the customer app.
    const vendorOrigin = requireVendorBaseUrl();

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
      await expect(page.getByRole("heading", { name: /ticket/i }).first()).toBeVisible();
    } else {
      test.info().annotations.push({
        type: "founder-gated",
        description:
          "Ticket purchase + wallet skipped — needs LENCO_SANDBOX (F9b). Asserted event PDP renders only.",
      });
      await expect(page).toHaveURL(new RegExp(`/e/${SEED.event.slug}`));
    }

    // ── Scanner verify + duplicate-reject leg (vendor app, OTP-gated) ─────────
    // Stable PIN fallback, minted per run by the canonical seed step — not the
    // rotating 60-second QR window code, which no stored secret could outlive.
    const scannerPin = ticketPin();
    if (!vendorOtpReady() || !scannerPin) {
      // One gate, two release-critical assertions: the first scan must verify
      // AND the second scan of the same ticket must be rejected. #657 Events
      // ships in this release, so neither may vanish into a skip.
      const missing: string[] = [];
      if (!vendorOtpReady()) missing.push("E2E_VENDOR_TEST_OTP");
      if (!scannerPin) missing.push("E2E_TICKET_PIN");
      const gate = resolveGate({
        kind: "REQUIRED_STRICT",
        journey: "event scanner verify + duplicate-reject",
        fixtures: missing,
      });
      enforceGate(gate);
      test.info().annotations.push({ type: "founder-gated", description: gate.reason });
      await page.goto(urlOn(vendorOrigin, `/events/${SEED.event.slug}/scan`));
      await expect(
        page
          .getByTestId("scan-pin-fallback")
          .or(page.getByTestId("scan-camera-loading"))
          .or(page.getByTestId("event-scan-count")),
      ).toBeVisible();
      test.skip(true, gate.reason);
      return;
    }

    // Organiser scanner — use the PIN/manual fallback to submit a ticket token.
    await page.goto(urlOn(vendorOrigin, `/events/${SEED.event.slug}/scan`));
    await page
      .getByTestId("scan-switch-pin")
      .click()
      .catch(() => {});
    const pinInput = page.getByTestId("scan-pin-fallback").getByRole("textbox");

    // First scan → verified.
    await pinInput.fill(scannerPin);
    await page
      .getByRole("button", { name: /verify|check|scan/i })
      .first()
      .click();
    await expect(page.getByTestId("scan-success")).toBeVisible({ timeout: 20_000 });

    // Second scan of the same ticket → duplicate rejected (not a success).
    await pinInput.fill(scannerPin);
    await page
      .getByRole("button", { name: /verify|check|scan/i })
      .first()
      .click();
    await expect(page.getByText(/already|duplicate|used|rejected/i).first()).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByTestId("scan-success")).toBeHidden();
  });
});
