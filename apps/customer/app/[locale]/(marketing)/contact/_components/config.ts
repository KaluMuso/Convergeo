/** Support contact configuration, resolved from env (NEXT_PUBLIC_SUPPORT_WHATSAPP). */

/**
 * Vergeo5 support line (founder-confirmed 2026-11-08); env overrides it. This is the
 * real support number, not a placeholder, so it is safe in production builds.
 */
const FALLBACK_WHATSAPP = "260761359005";

/**
 * Digits-only WhatsApp number for wa.me deep links. Typed nullable so callers keep
 * hiding the WhatsApp CTA if the line is ever withdrawn (no fake numbers).
 */
export function getSupportWhatsappNumber(): string | null {
  const digits = (process.env.NEXT_PUBLIC_SUPPORT_WHATSAPP ?? "").replace(/[^0-9]/g, "");
  return digits || FALLBACK_WHATSAPP;
}

/** Build a wa.me deep link with an optional prefilled message; `null` when unconfigured. */
export function buildWhatsappLink(prefill?: string): string | null {
  const number = getSupportWhatsappNumber();
  if (!number) {
    return null;
  }
  const base = `https://wa.me/${number}`;
  return prefill ? `${base}?text=${encodeURIComponent(prefill)}` : base;
}

const FALLBACK_SUPPORT_EMAIL = "support@vergeo5.com";

/** Customer support mailbox (NEXT_PUBLIC_SUPPORT_EMAIL, default support@vergeo5.com). */
export function getSupportEmail(): string {
  const raw = process.env.NEXT_PUBLIC_SUPPORT_EMAIL?.trim();
  return raw && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(raw) ? raw : FALLBACK_SUPPORT_EMAIL;
}
