/**
 * Zambian phone-number shaping shared by every OTP-driving spec/helper.
 *
 * PhoneForm's national-number field takes ONLY the 9-digit national
 * significant number — the `+260` country code is a fixed, read-only prefix
 * rendered separately by the component (see otp-login.ts and
 * auth-otp.spec.ts) — so filling a raw E.164 fixture phone into that field is
 * always wrong, regardless of which persona it belongs to. This was the exact
 * defect in Customer OTP (E2E run #52, RC-2): `customerOtp.testPhone`
 * (`+260970000001`) was filled in full, so the app's own client-side
 * normalizer read it as `260970000` and rejected it before any OTP was ever
 * requested.
 */

const ZAMBIAN_E164_PATTERN = /^\+260([79]\d{8})$/;

/**
 * Extract the 9-digit Zambian national significant number from a full E.164
 * fixture phone, e.g. `+260970000001` -> `970000001`.
 *
 * Fails closed: throws on anything that is not a well-formed `+260[7|9]XXXXXXXX`
 * fixture number, rather than silently returning a truncated or wrong
 * national number that a real OTP send could still (incorrectly) accept.
 */
export function nationalNumberFromE164(e164: string): string {
  const match = ZAMBIAN_E164_PATTERN.exec(e164.trim());
  if (!match || !match[1]) {
    throw new Error(
      `nationalNumberFromE164: "${e164}" is not a well-formed Zambian E.164 fixture phone ` +
        `(expected +260 followed by a 9-digit number starting 7 or 9)`,
    );
  }
  return match[1];
}
