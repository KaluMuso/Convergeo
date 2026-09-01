const E164_PATTERN = /^\+[1-9]\d{1,14}$/;

/**
 * Format a Supabase Auth phone for Africa's Talking international `to` field.
 *
 * Hosted Supabase Auth may store phones without a leading "+" (e.g. `260970000001`).
 * AT requires international format with "+" (e.g. `+260970000001`).
 */
export function formatPhoneForAt(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) {
    throw new Error("phone is empty");
  }

  let candidate: string;
  if (trimmed.startsWith("+")) {
    candidate = trimmed;
  } else if (/^\d+$/.test(trimmed)) {
    candidate = `+${trimmed}`;
  } else {
    throw new Error("phone is not in international format");
  }

  if (!E164_PATTERN.test(candidate)) {
    throw new Error("phone is not valid E.164");
  }

  return candidate;
}
