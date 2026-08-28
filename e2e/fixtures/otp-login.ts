import { expect, type Page } from "@playwright/test";

import { path, requireVendorBaseUrl, urlOn, vendorOtp } from "./env";
import { nationalNumberFromE164 } from "./phone";

export type LoginVendorViaOtpOptions = {
  /**
   * Locale-prefixed path (e.g. "/en/events/{slug}/scan") to land on after a
   * successful verify — passed through the real login flow's `next` param
   * (PhoneForm -> OtpForm -> navigateAfterPortalAuth), so the same
   * destination that proves the session is the one the caller actually
   * needs next. Defaults to "/services": a real, vendor-role-gated route
   * (packages/auth/src/middleware.ts `resolveGatedRedirect`) an anonymous
   * visitor is bounced away from, so simply arriving there IS the
   * authentication proof — no separate assertion needed.
   */
  next?: string;
};

/**
 * Drive the REAL Vendor phone-OTP login UI end to end and land on a
 * protected Vendor route:
 *
 *   anonymous -> Vendor /login (PhoneForm) -> real staging signInWithOtp
 *   -> Vendor /otp (OtpForm) -> real staging verifyOtp -> Supabase session
 *   -> protected Vendor route an anonymous visitor cannot reach.
 *
 * Every step is a real DOM interaction against the deployed Vendor app —
 * no localStorage/cookie fabrication, no service_role in the browser, no
 * direct DB session insertion, no `window.__VERGEO_E2E_SESSION__`, no mock
 * session, no hidden route. Callers MUST gate on `vendorOtpReady()` first
 * (see vendor-sell.spec.ts / event-ticket.spec.ts) — this helper assumes the
 * OTP fixture is present and throws loudly if the flow does not reach the
 * expected destination.
 */
export async function loginVendorViaOtp(
  page: Page,
  options: LoginVendorViaOtpOptions = {},
): Promise<void> {
  const vendorOrigin = requireVendorBaseUrl();
  const destination = options.next ?? path("/services");

  await page.goto(urlOn(vendorOrigin, `/login?next=${encodeURIComponent(destination)}`));

  // Same ambiguity note as auth-otp.spec.ts: PhoneForm's FormField renders in
  // `asGroup` mode, so a single semantic textbox query (not getByLabel) is
  // required to resolve to exactly the national-number input.
  const phoneInput = page.getByRole("textbox", { name: /phone|mobile/i });
  await expect(phoneInput).toBeVisible();
  // The field takes only the national number — the country code (+260) is a
  // fixed, read-only prefix rendered separately by PhoneForm. The canonical
  // Vendor phone is already a Zambian E.164 number; nationalNumberFromE164
  // extracts exactly that national number (shared with auth-otp.spec.ts —
  // see fixtures/phone.ts — instead of duplicating the slice logic here).
  await phoneInput.fill(nationalNumberFromE164(vendorOtp.testPhone));

  await page
    .getByRole("button", { name: /continue|send|next|get code/i })
    .first()
    .click();

  // Real staging signInWithOtp dispatch lands on Vendor /otp with ?phone=...
  await page.waitForURL(/\/otp(\?|$)/, { timeout: 20_000 });

  // OtpField (packages/ui/src/otp-field.tsx) has no autofocus — the exact PR
  // #680 lesson: page.keyboard.type() sends keystrokes to whatever currently
  // has DOM focus, which is nothing until a digit box is explicitly focused.
  await page.getByRole("textbox", { name: "Digit 1 of 6" }).click();
  for (const digit of vendorOtp.staticCode.slice(0, 6).split("")) {
    await page.keyboard.type(digit);
  }

  await page
    .getByRole("button", { name: /verify|submit|continue/i })
    .first()
    .click();

  // Real OtpForm -> supabase.auth.verifyOtp -> navigateAfterPortalAuth(portal:
  // "vendor") -> the destination. Middleware's vendor-role gate is what makes
  // arrival here proof: an anonymous or non-vendor session is bounced to
  // /login or /onboarding instead, so this assertion fails loudly rather than
  // treating "no error thrown" as success.
  const destinationPattern = new RegExp(`${destination.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`);
  await page.waitForURL(destinationPattern, { timeout: 20_000 });
  await expect(page).toHaveURL(destinationPattern);
  await expect(page).not.toHaveURL(/\/(login|otp)(\?|$)/);
}
