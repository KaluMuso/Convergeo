import { path, requireVendorBaseUrl, ticketPin, urlOn, vendorOtpReady } from "../fixtures/env";
import { enforceGate, resolveGate } from "../fixtures/gating";
import { sandboxEnabled } from "../fixtures/lenco";
import { loginVendorViaOtp } from "../fixtures/otp-login";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

/**
 * Critical path: buy an event ticket → see it in the wallet → organiser scanner
 * verifies it → a second check-in of the same ticket is rejected (single-use).
 *
 * Legs and their gates:
 *  - Ticket PURCHASE is a Lenco charge → gated behind `LENCO_SANDBOX` (F9b).
 *  - Scanner VERIFY / duplicate-reject runs on the vendor app (separate origin)
 *    and needs an organiser session → gated behind OTP test creds. Its canonical
 *    ticket is issued through the real FREE-RSVP service path; the private
 *    `E2E_TICKET_PIN` lets this leg run without forging a paid purchase.
 *
 * The scanner leg drives the EVENT scanner's manual fallback (`event-scan-*`),
 * not the order-pickup scanner: the event surface identifies a ticket by
 * `{ticketId, pin}` and checks it in through `POST /tickets/verify`, which is a
 * different endpoint, payload and authorization path from order pickup.
 */
test.describe("event · ticket lifecycle", () => {
  test("buy → wallet → scan verify → duplicate rejected", async ({ page }) => {
    // The scanner legs below navigate the vendor origin directly; in a strict
    // certification run an unset/collapsed vendor target fails here rather
    // than silently scanning on the customer app.
    const vendorOrigin = requireVendorBaseUrl();

    // Event PDP (customer app, public slug).
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
    // Stable, environment-bound PIN fallback derived by the canonical seed —
    // not the rotating 60-second QR code, which no stored value could outlive.
    const scannerPin = ticketPin();
    // The organiser scanner route and the verify API are both keyed on the
    // event's primary key, never its public slug.
    const scanRoute = path(`/events/${SEED.event.id}/scan`);

    if (!vendorOtpReady() || !scannerPin) {
      // One gate, two release-critical assertions: the first check-in must
      // verify AND the second check-in of the same ticket must be rejected.
      // #657 Events ships in this release, so neither may vanish into a skip.
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
      await page.goto(urlOn(vendorOrigin, scanRoute));
      await expect(
        page
          .getByTestId("event-scan-manual-fallback")
          .or(page.getByTestId("event-scan-camera-loading"))
          .or(page.getByTestId("event-scan-count")),
      ).toBeVisible();
      test.skip(true, gate.reason);
      return;
    }

    // Authenticate as the seeded organiser vendor via the REAL phone-OTP login
    // UI (same helper as vendor-sell) — establishes WHO is scanning. The
    // ticket id + PIN below identify WHICH ticket; the two are deliberately
    // independent, and the server re-checks both on every verify call.
    // Lands directly on the scanner: a route an anonymous visitor cannot
    // reach, which is itself the auth proof.
    await loginVendorViaOtp(page, { next: scanRoute });
    await expect(page).toHaveURL(new RegExp(`/events/${SEED.event.id}/scan`));

    // Organiser scanner. The body only mounts once the event detail request
    // resolves, so nothing below may be probed before then: an immediate
    // isVisible() on the switch answers "false" during loading and silently
    // skips the click, which then strands a camera-capable browser on the
    // camera view. Wait for the scanner to SETTLE into one of its two
    // supported states first — manual already open (camera unavailable or
    // denied, the headless default) or the camera running with its switch
    // offered — and only then decide. `.or()` polls until one appears, so this
    // absorbs slow event loading without a sleep or a timeout bump.
    const scannerRoot = page.getByTestId("event-scan-root");
    const manualForm = page.getByTestId("event-scan-manual-fallback");
    const switchToManual = page.getByTestId("event-scan-switch-manual");

    await expect(scannerRoot).toBeVisible({ timeout: 20_000 });
    await expect(manualForm.or(switchToManual)).toBeVisible({ timeout: 20_000 });
    // Evaluated only after the state settled, so it reflects a real state
    // rather than a still-loading screen. The two states are mutually
    // exclusive in ScannerView, so this cannot double-match.
    if (await switchToManual.isVisible()) {
      await switchToManual.click();
    }
    await expect(manualForm).toBeVisible();

    // Pin the SEEDED instance rather than inheriting pickDefaultInstance()'s
    // choice, which is "earliest upcoming, else instances[0]" and would follow
    // the seed data if it ever grew a second session. The picker only renders
    // when the event has more than one instance, so select it when present and
    // assert the effective identity either way — that attribute is what the
    // verify call actually carries.
    const instancePicker = page.getByTestId("event-scan-instance-select");
    if (await instancePicker.isVisible()) {
      await instancePicker.selectOption(SEED.event.instanceId);
    }
    await expect(scannerRoot).toHaveAttribute("data-instance-id", SEED.event.instanceId);
    await expect(scannerRoot).toHaveAttribute("data-event-id", SEED.event.id);

    const ticketIdInput = manualForm.getByTestId("event-scan-manual-ticket-id");
    const pinInput = manualForm.getByTestId("event-scan-manual-pin");
    const submit = manualForm.getByTestId("event-scan-manual-submit");

    // First check-in → verified by the server, not by the browser.
    await ticketIdInput.fill(SEED.event.ticketId);
    await pinInput.fill(scannerPin);
    await submit.click();
    const accepted = page.getByTestId("event-scan-flash-success");
    await expect(accepted).toBeVisible({ timeout: 20_000 });
    await expect(accepted).toHaveAttribute("data-scan-result-kind", "valid");

    // Second check-in of the same ticket → rejected BECAUSE it was already
    // spent. Single-use is enforced in `POST /tickets/verify`
    // (`ticket_already_checked_in` → the `conflict` kind), so the assertion
    // names that kind: every failure renders the same `event-scan-flash-error`
    // testid, and the old message regex also matched "rejected", so a wrong
    // PIN, a 403, an unknown ticket or an offline submit would all have passed
    // as proof of single-use enforcement. Those are real failures of this leg,
    // not evidence for it.
    await ticketIdInput.fill(SEED.event.ticketId);
    await pinInput.fill(scannerPin);
    await submit.click();
    const rejection = page.getByTestId("event-scan-flash-error");
    await expect(rejection).toBeVisible({ timeout: 20_000 });
    await expect(rejection).toHaveAttribute("data-scan-result-kind", "conflict");
    // `conflict` is not overridable from the flash: no override form may be
    // offered on a spent ticket.
    await expect(rejection.getByRole("button", { name: /override/i })).toHaveCount(0);
    await expect(page.getByTestId("event-scan-flash-success")).toBeHidden();
  });
});
