type Messages = { [key: string]: string | Messages };

/** True when a notifications-style leaf is `{ "__fallback": "en" }` (not a real string). */
export function isFallbackMarker(value: unknown): boolean {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const keys = Object.keys(value as Record<string, unknown>);
  return keys.length === 1 && keys[0] === "__fallback";
}

/**
 * Overlay locale-specific messages onto an English base.
 * - String leaves in `overlay` win.
 * - Objects merge recursively.
 * - `__fallback` marker objects are skipped (keep English).
 * - Top-level `__fallback` metadata keys are ignored.
 */
export function deepMergeMessages(base: Messages, overlay: Messages): Messages {
  const out: Messages = { ...base };

  for (const [key, value] of Object.entries(overlay)) {
    if (key === "__fallback") {
      continue;
    }
    if (isFallbackMarker(value)) {
      continue;
    }
    if (typeof value === "string") {
      out[key] = value;
      continue;
    }
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      const existing = out[key];
      const baseChild =
        existing !== null && typeof existing === "object" && !Array.isArray(existing)
          ? (existing as Messages)
          : {};
      out[key] = deepMergeMessages(baseChild, value as Messages);
    }
  }

  return out;
}
