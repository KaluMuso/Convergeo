/**
 * T28 — on-device phone normalisation + SHA-256 (E.164). Raw numbers never leave the device.
 */

/** Normalise Zambian mobiles to E.164 (+260…); other numbers keep a leading +. */
export function normalizeToE164(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("+")) {
    const digits = `+${trimmed.slice(1).replace(/\D/g, "")}`;
    return digits.length > 1 ? digits : null;
  }
  const digits = trimmed.replace(/\D/g, "");
  if (!digits) return null;
  if (digits.length === 10 && digits.startsWith("0")) {
    return `+260${digits.slice(1)}`;
  }
  if (digits.length === 9 && /^[79][5-7]\d{7}$/.test(digits)) {
    return `+260${digits}`;
  }
  if (digits.startsWith("260")) {
    return `+${digits}`;
  }
  if (digits.length >= 10) {
    return `+${digits}`;
  }
  return null;
}

export function isZambianMobileE164(e164: string): boolean {
  return /^\+260[79][5-7]\d{7}$/.test(e164);
}

export async function sha256HexUtf8(value: string): Promise<string> {
  const data = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Hash a contact number for discovery API (post-normalisation). */
export async function hashContactPhone(raw: string): Promise<string | null> {
  const e164 = normalizeToE164(raw);
  if (!e164) return null;
  return sha256HexUtf8(e164);
}

export function waMeInviteLink(e164: string, text: string): string {
  const phone = e164.replace(/^\+/, "");
  return `https://wa.me/${encodeURIComponent(phone)}?text=${encodeURIComponent(text)}`;
}

export function waMeShareLink(text: string): string {
  return `https://wa.me/?text=${encodeURIComponent(text)}`;
}

/** wa.me deep link from raw msisdn (digits or +E.164) with prefilled text; null when invalid. */
export function waMeLinkFromRaw(raw: string, text: string): string | null {
  const e164 = normalizeToE164(raw);
  if (!e164) {
    return null;
  }
  return waMeInviteLink(e164, text);
}

export function supportsContactPicker(): boolean {
  return typeof navigator !== "undefined" && "contacts" in navigator;
}
