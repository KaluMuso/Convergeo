/**
 * Pure helpers for the advertising board (no React, unit-tested).
 *
 * Schedules are entered and shown in Africa/Lusaka (CAT, UTC+02:00, no DST)
 * regardless of the admin's browser time zone, so "starts 08:00" always means
 * 08:00 in Lusaka.
 */

export const LUSAKA_OFFSET = "+02:00";
const LUSAKA_OFFSET_MS = 2 * 60 * 60 * 1000;

export const TARGET_KINDS = ["listing", "product", "service", "event", "vendor"] as const;
export type TargetKind = (typeof TARGET_KINDS)[number];

export type AdTarget = {
  kind: TargetKind;
  id: string;
  label: string;
  status: string;
  visible: boolean;
  href: string;
};

/** ISO instant → `datetime-local` value in Lusaka wall-clock time. */
export function toLusakaInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Date(date.getTime() + LUSAKA_OFFSET_MS).toISOString().slice(0, 16);
}

/** `datetime-local` value typed as Lusaka wall-clock time → ISO instant (UTC). */
export function fromLusakaInput(value: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null;
  const date = new Date(`${value}:00${LUSAKA_OFFSET}`);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

export function isValidWindow(startsAt: string | null, endsAt: string | null): boolean {
  return !!startsAt && !!endsAt && new Date(endsAt).getTime() > new Date(startsAt).getTime();
}

/** Placements whose content may still be edited (the server rejects ended ones). */
export function isEditable(status: string): boolean {
  return status !== "ended";
}

export function isValidReason(reason: string): boolean {
  return reason.trim().length >= 3;
}
