/**
 * Readiness checklist model for event collaboration. Mirrors
 * services/api/app/services/events/collaboration.py (11 items, same rules) so the
 * percentage shown here equals the one the API stores. The API stays the authority;
 * this only drives the UI.
 */

export type EquipmentState = "ready" | "needed" | "not_needed";
export type PermitState = "obtained" | "pending" | "not_required";
export const EQUIPMENT_ITEMS = [
  "sound",
  "stage",
  "power",
  "seating",
  "security",
] as const;
export type EquipmentItem = (typeof EQUIPMENT_ITEMS)[number];
export const MAX_BPS = 10_000;

export type TicketTier = {
  name: string;
  price_ngwee: number;
  qty_cap: number | null;
};

export type Checklist = {
  venue: {
    name: string | null;
    landmark: string | null;
    lat: number | null;
    lng: number | null;
  };
  schedule: { starts_at: string | null; ends_at: string | null };
  capacity: { capacity: number | null };
  equipment: Record<EquipmentItem, EquipmentState | null>;
  permits: { status: PermitState | null; note: string | null };
  tiers: TicketTier[];
};

export type EventDraftFields = {
  title: string | null;
  category: string | null;
  description: string | null;
  city: string | null;
};

export type FieldError = { field: string; code: string };

export function emptyChecklist(): Checklist {
  return {
    venue: { name: null, landmark: null, lat: null, lng: null },
    schedule: { starts_at: null, ends_at: null },
    capacity: { capacity: null },
    equipment: {
      sound: null,
      stage: null,
      power: null,
      seating: null,
      security: null,
    },
    permits: { status: null, note: null },
    tiers: [],
  };
}

export function emptyDraft(): EventDraftFields {
  return { title: null, category: null, description: null, city: null };
}

/** Merge a stored (possibly partial) checklist onto the empty shape. */
export function normaliseChecklist(
  raw: Record<string, unknown> | null | undefined,
): Checklist {
  const base = emptyChecklist();
  if (!raw) {
    return base;
  }
  const r = raw as Partial<Checklist>;
  return {
    venue: { ...base.venue, ...(r.venue ?? {}) },
    schedule: { ...base.schedule, ...(r.schedule ?? {}) },
    capacity: { ...base.capacity, ...(r.capacity ?? {}) },
    equipment: { ...base.equipment, ...(r.equipment ?? {}) },
    permits: { ...base.permits, ...(r.permits ?? {}) },
    tiers: Array.isArray(r.tiers)
      ? r.tiers.map((t) => ({
          name: t.name,
          price_ngwee: t.price_ngwee,
          qty_cap: t.qty_cap ?? null,
        }))
      : [],
  };
}

export function normaliseDraft(
  raw: Record<string, unknown> | null | undefined,
): EventDraftFields {
  const base = emptyDraft();
  if (!raw) {
    return base;
  }
  const r = raw as Partial<EventDraftFields>;
  return {
    title: r.title ?? null,
    category: r.category ?? null,
    description: r.description ?? null,
    city: r.city ?? null,
  };
}

export type ReadinessKey =
  | "venue"
  | "schedule"
  | "capacity"
  | `equipment_${EquipmentItem}`
  | "permits"
  | "tiers"
  | "revenue_share";

function filled(value: string | null | undefined): boolean {
  return typeof value === "string" && value.trim().length > 0;
}

export function readinessItems(
  checklist: Checklist,
  revenueShareBps: number | null,
): Record<ReadinessKey, boolean> {
  const { venue, schedule } = checklist;
  const starts = schedule.starts_at
    ? Date.parse(schedule.starts_at)
    : Number.NaN;
  const ends = schedule.ends_at ? Date.parse(schedule.ends_at) : Number.NaN;
  const items = {
    venue:
      filled(venue.name) &&
      filled(venue.landmark) &&
      venue.lat !== null &&
      venue.lng !== null,
    schedule: Number.isFinite(starts) && Number.isFinite(ends) && ends > starts,
    capacity: checklist.capacity.capacity !== null,
    permits:
      checklist.permits.status === "obtained" ||
      checklist.permits.status === "not_required",
    tiers: checklist.tiers.length > 0,
    revenue_share: revenueShareBps !== null,
  } as Record<ReadinessKey, boolean>;
  for (const item of EQUIPMENT_ITEMS) {
    const state = checklist.equipment[item];
    items[`equipment_${item}`] = state === "ready" || state === "not_needed";
  }
  return items;
}

export function readinessPct(
  checklist: Checklist,
  revenueShareBps: number | null,
): number {
  const items = Object.values(readinessItems(checklist, revenueShareBps));
  return Math.round((100 * items.filter(Boolean).length) / items.length);
}

/** Percent typed by the vendor (0-100, up to 2 decimals) -> integer basis points. */
export function percentToBps(percent: number): number {
  return Math.round(percent * 100);
}

export function bpsToPercent(bps: number): number {
  return bps / 100;
}

/** Parse a percent text box. Returns null when empty or out of 0-100. */
export function parsePercentInput(text: string): number | null {
  const trimmed = text.trim().replace(",", ".");
  if (!/^\d{1,3}(\.\d{1,2})?$/.test(trimmed)) {
    return null;
  }
  const value = Number(trimmed);
  return value >= 0 && value <= 100 ? percentToBps(value) : null;
}

/** Whole kwacha text -> integer ngwee without floating point maths on money. */
export function kwachaToNgwee(text: string): number | null {
  const trimmed = text.trim().replace(",", ".");
  const match = /^(\d{1,9})(?:\.(\d{1,2}))?$/.exec(trimmed);
  if (!match) {
    return null;
  }
  return (
    Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0") || "0")
  );
}

export function ngweeToKwachaText(ngwee: number): string {
  const whole = Math.floor(ngwee / 100);
  const cents = ngwee % 100;
  return cents === 0
    ? String(whole)
    : `${whole}.${String(cents).padStart(2, "0")}`;
}

/** Same blockers the API reports on submit (field, code). */
export function submitErrors(
  draft: EventDraftFields,
  checklist: Checklist,
  revenueShareBps: number | null,
  now: Date = new Date(),
): FieldError[] {
  const errors: FieldError[] = [];
  const add = (field: string, code: string) => errors.push({ field, code });
  if (!filled(draft.title)) add("event_draft.title", "required");
  if (!filled(draft.category)) add("event_draft.category", "required");
  const { venue, schedule } = checklist;
  if (!filled(venue.name)) add("checklist.venue.name", "required");
  if (!filled(venue.landmark)) add("checklist.venue.landmark", "required");
  if (venue.lat === null || venue.lng === null)
    add("checklist.venue.gps", "required");
  const starts = schedule.starts_at
    ? Date.parse(schedule.starts_at)
    : Number.NaN;
  const ends = schedule.ends_at ? Date.parse(schedule.ends_at) : Number.NaN;
  if (!Number.isFinite(starts)) add("checklist.schedule.starts_at", "required");
  else if (starts <= now.getTime())
    add("checklist.schedule.starts_at", "must_be_future");
  if (!Number.isFinite(ends)) add("checklist.schedule.ends_at", "required");
  else if (Number.isFinite(starts) && ends <= starts) {
    add("checklist.schedule.ends_at", "must_be_after_start");
  }
  const capacity = checklist.capacity.capacity;
  if (capacity === null) add("checklist.capacity.capacity", "required");
  for (const item of EQUIPMENT_ITEMS) {
    if (checklist.equipment[item] === null)
      add(`checklist.equipment.${item}`, "required");
  }
  if (checklist.permits.status === null)
    add("checklist.permits.status", "required");
  if (checklist.tiers.length === 0) add("checklist.tiers", "required");
  checklist.tiers.forEach((tier, index) => {
    if (capacity !== null && tier.qty_cap !== null && tier.qty_cap > capacity) {
      add(`checklist.tiers.${index}.qty_cap`, "exceeds_capacity");
    }
  });
  if (revenueShareBps === null) add("revenue_share_bps", "required");
  return errors;
}

/** Map an API field path to the i18n section label key under events.collab.sections. */
export function sectionForField(field: string): string {
  if (field.startsWith("event_draft")) return "event";
  if (field.startsWith("revenue_share")) return "share";
  const parts = field.split(".");
  return parts[1] ?? "event";
}
