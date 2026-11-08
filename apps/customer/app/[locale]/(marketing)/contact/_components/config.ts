/** Support contact configuration, resolved from env (NEXT_PUBLIC_SUPPORT_WHATSAPP). */

/** Vergeo5 support line (founder-confirmed 2026-11-08); env overrides it. */
const FALLBACK_WHATSAPP = "260761359005";

/** Digits-only WhatsApp number for wa.me deep links. */
export function getSupportWhatsappNumber(): string {
  const raw = process.env.NEXT_PUBLIC_SUPPORT_WHATSAPP ?? FALLBACK_WHATSAPP;
  return raw.replace(/[^0-9]/g, "") || FALLBACK_WHATSAPP;
}

/** Build a wa.me deep link with an optional prefilled message. */
export function buildWhatsappLink(prefill?: string): string {
  const number = getSupportWhatsappNumber();
  const base = `https://wa.me/${number}`;
  return prefill ? `${base}?text=${encodeURIComponent(prefill)}` : base;
}
