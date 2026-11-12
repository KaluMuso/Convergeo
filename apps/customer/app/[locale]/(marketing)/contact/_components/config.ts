/** Support contact configuration, resolved from env. No fake numbers in production. */

/** Dev-only placeholder so local pages render the CTA; NEVER used in production builds. */
const DEV_FALLBACK_WHATSAPP = "260970000000";

/**
 * Digits-only WhatsApp number for wa.me deep links, or `null` when unconfigured in
 * production (callers must hide the WhatsApp CTA rather than link to a fake number).
 */
export function getSupportWhatsappNumber(): string | null {
  const digits = (process.env.NEXT_PUBLIC_SUPPORT_WHATSAPP ?? "").replace(/[^0-9]/g, "");
  if (digits) {
    return digits;
  }
  return process.env.NODE_ENV === "production" ? null : DEV_FALLBACK_WHATSAPP;
}

/** Build a wa.me deep link with an optional prefilled message; `null` when unconfigured in prod. */
export function buildWhatsappLink(prefill?: string): string | null {
  const number = getSupportWhatsappNumber();
  if (!number) {
    return null;
  }
  const base = `https://wa.me/${number}`;
  return prefill ? `${base}?text=${encodeURIComponent(prefill)}` : base;
}
