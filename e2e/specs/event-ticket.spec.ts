import {
  path,
  requireVendorBaseUrl,
  ticketPin,
  urlOn,
  vendorOtp,
  vendorOtpReady,
} from "../fixtures/env";
import { enforceGate, resolveGate } from "../fixtures/gating";
import { loginVendorViaOtp } from "../fixtures/otp-login";
import { missingOutboundApproval } from "../fixtures/outbound-approval";
import {
  buyPaidTicket,
  loginPaidBuyer,
  missingPaidPrerequisites,
  settleSandboxTicket,
  verifyPaidTicketSpine,
} from "../fixtures/paid-ticket";
import {
  expect,
  fillScannerCredential,
  SCANNER_ARTIFACT_POLICY,
  test,
} from "../fixtures/scanner-artifact-test";
import { SEED } from "../fixtures/seed";

test.use(SCANNER_ARTIFACT_POLICY);
test.use({ serviceWorkers: "block" });

/** Both paths use the same real organiser admission surface, with different tickets. */
async function scanTicket(
  page: import("@playwright/test").Page,
  ticketId: string,
  scannerPin: string,
): Promise<void> {
  requireVendorBaseUrl();
  const scanRoute = path(`/events/${SEED.event.id}/scan`);
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
    try {
      await switchToManual.click({ timeout: 3_000 });
    } catch (error) {
      // Camera permission can settle between isVisible and click, replacing
      // the switch with the manual form. Accept only that actual UI state.
      try {
        await expect(manualForm).toBeVisible({ timeout: 5_000 });
      } catch {
        throw error;
      }
    }
  }
  await expect(manualForm).toBeVisible();

  // Pin the canonical instance rather than inheriting pickDefaultInstance()'s
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
  await ticketIdInput.fill(ticketId);
  await fillScannerCredential(pinInput, scannerPin);
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
  await ticketIdInput.fill(ticketId);
  await fillScannerCredential(pinInput, scannerPin);
  await submit.click();
  const rejection = page.getByTestId("event-scan-flash-error");
  await expect(rejection).toBeVisible({ timeout: 20_000 });
  await expect(rejection).toHaveAttribute("data-scan-result-kind", "conflict");
  // `conflict` is not overridable from the flash: no override form may be
  // offered on a spent ticket.
  await expect(rejection.getByRole("button", { name: /override/i })).toHaveCount(0);
  await expect(page.getByTestId("event-scan-flash-success")).toBeHidden();
}

test.describe("event · ticket lifecycle", () => {
  test("paid order → issued wallet ticket → organiser admission → duplicate rejected", async ({
    page,
  }) => {
    test.setTimeout(420_000);
    const missing = missingPaidPrerequisites();
    if (missing.length) {
      const gate = resolveGate({
        kind: "REQUIRED_STRICT",
        journey: "paid ticket order through admission",
        fixtures: missing,
      });
      enforceGate(gate);
      test.info().annotations.push({ type: "founder-gated", description: gate.reason });
      test.skip(true, gate.reason);
      return;
    }
    // Validate scanner origin before any charge, then sign in through real OTP.
    requireVendorBaseUrl();
    await loginPaidBuyer(page);
    const { purchase, bearer, apiOrigin } = await buyPaidTicket(page);
    // The companion checkout UI handles /checkout?group. This acceptance path
    // charges the captured ticket order through the established MoMo retry endpoint.
    const payment = await settleSandboxTicket(apiOrigin, bearer, purchase);
    const { ticketId, pin } = await verifyPaidTicketSpine(apiOrigin, bearer, purchase, payment);
    await page.goto(path("/account/tickets"));
    await expect(page.locator(`a[href$="/account/tickets/${ticketId}"]`)).toBeVisible();
    await scanTicket(page, ticketId, pin);
  });

  test("independent free RSVP scanner verify → duplicate rejected", async ({ page }) => {
    const vendorOrigin = requireVendorBaseUrl();
    await page.goto(path(`/e/${SEED.event.slug}`));
    await expect(page).toHaveURL(new RegExp(`/e/${SEED.event.slug}`));
    const scannerPin = ticketPin();
    const scanRoute = path(`/events/${SEED.event.id}/scan`);
    const missingApproval = missingOutboundApproval("otp", process.env, {
      persona: "vendor",
      recipientPhone: vendorOtp.testPhone,
    });
    if (!vendorOtpReady() || !scannerPin || missingApproval.length) {
      const missing: string[] = [];
      if (!vendorOtpReady()) missing.push("E2E_VENDOR_TEST_OTP");
      if (!scannerPin) missing.push("E2E_TICKET_PIN");
      missing.push(...missingApproval);
      const gate = resolveGate({
        kind: "REQUIRED_STRICT",
        journey: "free RSVP scanner verify + duplicate-reject",
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
    await scanTicket(page, SEED.event.ticketId, scannerPin);
  });
});
