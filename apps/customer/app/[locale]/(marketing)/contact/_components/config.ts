/** Support contact configuration, resolved from env (NEXT_PUBLIC_SUPPORT_WHATSAPP). */

/**
 * Digits-only support number for wa.me / tel links, or `null` when
 * NEXT_PUBLIC_SUPPORT_WHATSAPP is not configured. Owner decision (2026-11-12): no
 * built-in fallback number in any environment; callers hide phone/WhatsApp CTAs.
 */
export function getSupportWhatsappNumber(): string | null {
  const digits = (process.env.NEXT_PUBLIC_SUPPORT_WHATSAPP ?? "").replace(/[^0-9]/g, "");
  return digits || null;
}

/** Display form of the configured support number ("+260761359005"), or `null`. */
export function getSupportPhoneDisplay(): string | null {
  const digits = getSupportWhatsappNumber();
  return digits ? `+${digits}` : null;
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
