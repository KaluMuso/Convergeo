/**
 * Clips pilot — pure helpers for the allowlist control (kept out of the
 * component so they are unit-testable without a DOM).
 */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const PILOT_NOTE_MAX = 280;

/** Trimmed, lower-cased vendor id, or `null` when it is not a UUID. */
export function normaliseVendorId(raw: string): string | null {
  const value = raw.trim().toLowerCase();
  return UUID_RE.test(value) ? value : null;
}

export type PilotPosture = "off" | "pilot" | "open";

/**
 * What the founder needs to know at a glance:
 * - `off`   — the `clips` flag is off: nothing is live, the list is preparation only;
 * - `pilot` — flag on, allowlist enforced: only listed vendors upload and are seen;
 * - `open`  — flag on, allowlist not enforced: the pilot has ended.
 */
export function pilotPosture(state: {
  clips_enabled: boolean;
  allowlist_enforced: boolean;
}): PilotPosture {
  if (!state.clips_enabled) return "off";
  return state.allowlist_enforced ? "pilot" : "open";
}

/** Client-side mirror of the API's checks, so the form can explain itself. */
export function validatePilotAdd(
  vendorIdRaw: string,
  note: string,
  existing: readonly string[],
  maxVendors: number,
): { ok: true; vendorId: string } | { ok: false; errorKey: string } {
  const vendorId = normaliseVendorId(vendorIdRaw);
  if (!vendorId) return { ok: false, errorKey: "errors.invalidId" };
  if (note.length > PILOT_NOTE_MAX) return { ok: false, errorKey: "errors.noteTooLong" };
  if (existing.includes(vendorId)) return { ok: false, errorKey: "errors.alreadyListed" };
  if (existing.length >= maxVendors) return { ok: false, errorKey: "errors.full" };
  return { ok: true, vendorId };
}
