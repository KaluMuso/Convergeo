import { expect, type Page } from "@playwright/test";

import { BASE_URL, path, requireVendorBaseUrl, urlOn, vendorOtp, vendorOtpReady } from "./env";
import { nationalNumberFromE164 } from "./phone";

export type LoginVendorViaOtpOptions = {
  /** Locale-prefixed, vendor-role-gated destination; defaults to the locale's /services. */
  next?: string;
};

type Attempt = {
  destination: string;
  phase: "new" | "request-started" | "code-pending" | "verification-started" | "confirmed";
  pending?: Promise<void>;
};
const attempts = new WeakMap<Page, Attempt>();

/**
 * Drive the existing phone UI with a synthetic fixture only. Callers also gate
 * before navigation. No session fabrication, direct Auth request, resend or
 * explicit Verify click: the sixth digit drives the existing auto-submit.
 * An interrupted attempt stays associated with this Page; resume can await
 * navigation but cannot re-send or re-verify an accepted/uncertain request.
 */
export async function loginVendorViaOtp(
  page: Page,
  options: LoginVendorViaOtpOptions = {},
): Promise<void> {
  if (!vendorOtpReady()) {
    throw new Error(
      "vendor phone OTP requires a six-digit fixture and explicit attested transport",
    );
  }
  let national: string;
  try {
    national = nationalNumberFromE164(vendorOtp.testPhone);
  } catch {
    throw new Error("vendor phone OTP fixture is invalid");
  }
  let vendorOrigin: string;
  try {
    const vendor = new URL(requireVendorBaseUrl());
    if (
      vendor.username ||
      vendor.password ||
      vendor.origin === new URL(BASE_URL).origin ||
      !(
        vendor.protocol === "https:" ||
        (vendor.protocol === "http:" &&
          ["localhost", "127.0.0.1", "[::1]"].includes(vendor.hostname))
      )
    ) {
      throw new Error("invalid origin");
    }
    vendorOrigin = vendor.origin;
  } catch {
    throw new Error("vendor OTP requires a valid distinct portal origin");
  }
  const destination = options.next ?? path("/services");
  let target: URL;
  try {
    if (typeof destination !== "string") throw new Error("invalid destination");
    target = new URL(destination, vendorOrigin);
  } catch {
    throw new Error("vendor OTP destination must be a local protected route");
  }
  if (
    !destination.startsWith("/") ||
    destination.startsWith("//") ||
    /[\\\x00-\x20]/.test(destination) ||
    /%(?:2f|5c|00|0a|0d)/i.test(destination) ||
    target.origin !== vendorOrigin ||
    target.pathname !== destination.split(/[?#]/)[0] ||
    !target.pathname.startsWith(`${path("/")}/`) ||
    /\/(?:login|otp|onboarding|reset-password|health|api|_next|_vercel)(?:\/|$)/.test(
      target.pathname,
    ) ||
    /[.%]/.test(target.pathname)
  ) {
    throw new Error("vendor OTP destination must be a local protected route");
  }
  let attempt = attempts.get(page);
  if (attempt && attempt.destination !== target.href) {
    throw new Error("vendor OTP Page already belongs to another destination");
  }
  if (!attempt) {
    attempt = { destination: target.href, phase: "new" };
    attempts.set(page, attempt);
  }
  if (attempt.pending) return attempt.pending;
  const active = attempt;
  const otpRoute = (url: URL) =>
    url.origin === vendorOrigin &&
    url.pathname === path("/otp") &&
    url.searchParams.get("phone") === vendorOtp.testPhone;
  const confirmedRoute = (url: URL) => url.href === target.href;
  const pending = Promise.resolve().then(async () => {
    try {
      if (active.phase === "new") {
        await page.goto(urlOn(vendorOrigin, `/login?next=${encodeURIComponent(destination)}`));
        const phoneInput = page.getByRole("textbox", { name: /phone|mobile/i });
        await expect(phoneInput).toBeVisible();
        await phoneInput.fill(national);
        active.phase = "request-started"; // Set before click: interruption may hide acceptance.
        await page
          .getByRole("button", { name: /continue|send|next|get code/i })
          .first()
          .click();
      }
      if (active.phase === "request-started") {
        await page.waitForURL(otpRoute, { timeout: 20_000 });
        active.phase = "code-pending";
      }
      if (active.phase === "code-pending") {
        await page.waitForURL(otpRoute, { timeout: 20_000 });
        // Restart incomplete digit entry without requesting a second code.
        for (let digit = 1; digit <= 6; digit++) {
          await page.getByRole("textbox", { name: `Digit ${digit} of 6` }).fill("");
        }
        await page.getByRole("textbox", { name: "Digit 1 of 6" }).click();
        for (let index = 0; index < 6; index++) {
          if (index === 5) active.phase = "verification-started";
          await page.keyboard.type(vendorOtp.staticCode[index]!);
        }
      }
      await page.waitForURL(confirmedRoute, { timeout: 20_000 });
      await expect(page).toHaveURL(target.href);
      active.phase = "confirmed";
    } catch {
      throw new Error(
        `vendor OTP ${active.phase} incomplete; inspect before starting another request`,
      );
    }
  });
  active.pending = pending;
  try {
    await pending;
  } finally {
    active.pending = undefined;
  }
}
