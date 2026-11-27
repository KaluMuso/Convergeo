import {
  ARCHETYPE_SECTIONS,
  type DetailSection,
  type EventArchetype,
} from "@vergeo/ui/src/event-archetype";

/**
 * Editable form state for archetype details. Everything is a string (or a list of
 * string-valued rows) so inputs stay controlled; `draftToDetails` produces the exact
 * JSON the API validates (spec docs/plan/event-type-templates.md).
 */
export type Row = Record<string, string>;
export type MenuItemRow = {
  name: string;
  description: string;
  price: string;
  dietary: string;
};
export type MenuSectionRow = { title: string; items: MenuItemRow[] };

export type DetailsDraft = {
  scalars: Record<string, string>;
  rows: Record<string, Row[]>;
  lines: Record<string, string>;
  menu: MenuSectionRow[];
  presentedBy: Row;
};

export type FieldKind = "text" | "textarea" | "time" | "number" | "select";
export type FieldSpec = {
  key: string;
  kind: FieldKind;
  required?: boolean;
  max: number;
  options?: readonly string[];
};

export const SCALAR_SPECS: Readonly<Record<string, FieldSpec>> = {
  dress_code: { key: "dress_code", kind: "text", max: 80 },
  age_policy: {
    key: "age_policy",
    kind: "select",
    max: 20,
    options: ["all_ages", "guardian_under_12", "16_plus", "18_plus"],
  },
  doors_open: { key: "doors_open", kind: "time", max: 5 },
  merch_note: { key: "merch_note", kind: "text", max: 200 },
  denomination: { key: "denomination", kind: "text", max: 60 },
  donation_note: { key: "donation_note", kind: "textarea", max: 300 },
  livestream_url: { key: "livestream_url", kind: "text", max: 300 },
  family_bundle_note: { key: "family_bundle_note", kind: "textarea", max: 300 },
  seating_note: { key: "seating_note", kind: "textarea", max: 300 },
  reservation_note: { key: "reservation_note", kind: "textarea", max: 300 },
  host_name: { key: "host_name", kind: "text", max: 80 },
  promo_note: { key: "promo_note", kind: "text", max: 200 },
  giveaway_note: { key: "giveaway_note", kind: "text", max: 200 },
  host_names: { key: "host_names", kind: "text", max: 120 },
  occasion: { key: "occasion", kind: "text", max: 80 },
  rsvp_note: { key: "rsvp_note", kind: "textarea", max: 300 },
  gift_note: { key: "gift_note", kind: "textarea", max: 300 },
};

export type ListSpec = { fields: FieldSpec[]; max: number };

const SPONSOR_FIELDS: FieldSpec[] = [
  { key: "name", kind: "text", required: true, max: 80 },
  { key: "logo", kind: "text", max: 300 },
  { key: "link_url", kind: "text", max: 300 },
  { key: "tagline", kind: "text", max: 120 },
];

export const LIST_SPECS: Readonly<Record<string, ListSpec>> = {
  sponsors: { fields: SPONSOR_FIELDS, max: 6 },
  faqs: {
    fields: [
      { key: "question", kind: "text", required: true, max: 120 },
      { key: "answer", kind: "textarea", required: true, max: 500 },
    ],
    max: 8,
  },
  lineup: {
    fields: [
      { key: "name", kind: "text", required: true, max: 80 },
      {
        key: "role",
        kind: "select",
        max: 12,
        options: ["headliner", "support", "dj", "mc", "guest"],
      },
      { key: "stage", kind: "text", max: 60 },
      { key: "slot", kind: "time", max: 5 },
      { key: "image", kind: "text", max: 300 },
      { key: "bio", kind: "text", max: 200 },
    ],
    max: 30,
  },
  agenda: {
    fields: [
      { key: "time", kind: "time", required: true, max: 5 },
      { key: "title", kind: "text", required: true, max: 200 },
      { key: "speaker", kind: "text", max: 80 },
      { key: "notes", kind: "text", max: 300 },
    ],
    max: 30,
  },
  speakers: {
    fields: [
      { key: "name", kind: "text", required: true, max: 80 },
      { key: "role", kind: "text", max: 60 },
      { key: "image", kind: "text", max: 300 },
      { key: "bio", kind: "text", max: 200 },
    ],
    max: 12,
  },
  activities: {
    fields: [
      { key: "name", kind: "text", required: true, max: 80 },
      { key: "age_group", kind: "text", max: 40 },
      { key: "time", kind: "time", max: 5 },
      { key: "area", kind: "text", max: 60 },
    ],
    max: 20,
  },
  age_groups: {
    fields: [
      { key: "label", kind: "text", required: true, max: 40 },
      { key: "min_age", kind: "number", required: true, max: 3 },
      { key: "max_age", kind: "number", max: 3 },
    ],
    max: 8,
  },
  activations: {
    fields: [
      { key: "title", kind: "text", required: true, max: 80 },
      { key: "description", kind: "text", max: 200 },
    ],
    max: 8,
  },
};

export const PRESENTED_BY_FIELDS = SPONSOR_FIELDS;

/** One-per-line list sections: [section, maxLines, maxLineLength]. */
export const LINE_SPECS: Readonly<Record<string, readonly [number, number]>> = {
  stages: [6, 60],
  languages: [4, 30],
  bring_list: [10, 80],
};

export const MENU_LIMITS = { sections: 6, items: 12 } as const;
const DIETARY = ["vegetarian", "vegan", "halal", "gluten_free", "spicy"] as const;
export const DIETARY_OPTIONS = DIETARY;

export function emptyDraft(): DetailsDraft {
  return { scalars: {}, rows: {}, lines: {}, menu: [], presentedBy: {} };
}

/** "12.50" kwacha to integer ngwee without floats; null when malformed. */
export function kwachaToNgwee(input: string): number | null {
  const text = input.trim();
  if (!/^\d{1,7}(\.\d{1,2})?$/.test(text)) return null;
  const [whole = "0", frac = ""] = text.split(".");
  return Number.parseInt(whole, 10) * 100 + Number.parseInt(frac.padEnd(2, "0") || "0", 10);
}

export function ngweeToKwacha(ngwee: number): string {
  const whole = Math.floor(ngwee / 100);
  const frac = ngwee % 100;
  return frac === 0 ? String(whole) : `${whole}.${String(frac).padStart(2, "0")}`;
}

function s(value: unknown): string {
  return typeof value === "string" ? value : typeof value === "number" ? String(value) : "";
}

function toRows(value: unknown, fields: FieldSpec[]): Row[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    const source = (item ?? {}) as Record<string, unknown>;
    return Object.fromEntries(fields.map((f) => [f.key, s(source[f.key])]));
  });
}

/** API details JSON to editable draft. Unknown keys are ignored. */
export function detailsToDraft(raw: unknown): DetailsDraft {
  const src = (raw !== null && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const draft = emptyDraft();
  for (const key of Object.keys(SCALAR_SPECS)) draft.scalars[key] = s(src[key]);
  for (const [key, spec] of Object.entries(LIST_SPECS))
    draft.rows[key] = toRows(src[key], spec.fields);
  for (const key of Object.keys(LINE_SPECS)) {
    draft.lines[key] = Array.isArray(src[key]) ? (src[key] as unknown[]).map(s).join("\n") : "";
  }
  if (Array.isArray(src.menu_sections)) {
    draft.menu = (src.menu_sections as Record<string, unknown>[]).map((section) => ({
      title: s(section.title),
      items: (Array.isArray(section.items) ? (section.items as Record<string, unknown>[]) : []).map(
        (item) => ({
          name: s(item.name),
          description: s(item.description),
          price: typeof item.price_ngwee === "number" ? ngweeToKwacha(item.price_ngwee) : "",
          dietary: Array.isArray(item.dietary) ? (item.dietary as unknown[]).map(s).join(",") : "",
        }),
      ),
    }));
  }
  const presented = (src.presented_by ?? {}) as Record<string, unknown>;
  draft.presentedBy = Object.fromEntries(SPONSOR_FIELDS.map((f) => [f.key, s(presented[f.key])]));
  return draft;
}

function rowToJson(row: Row, fields: FieldSpec[]): Record<string, unknown> | null {
  const out: Record<string, unknown> = {};
  for (const field of fields) {
    const value = (row[field.key] ?? "").trim();
    if (!value) continue;
    out[field.key] = field.kind === "number" ? Number.parseInt(value, 10) : value;
  }
  return Object.keys(out).length ? out : null;
}

/**
 * Draft to API payload for the effective archetype only: sections the archetype does
 * not offer are dropped, blank rows and strings are omitted.
 */
export function draftToDetails(
  archetype: EventArchetype,
  draft: DetailsDraft,
): Record<string, unknown> {
  const sections = new Set<DetailSection>(ARCHETYPE_SECTIONS[archetype]);
  const out: Record<string, unknown> = {};
  for (const key of Object.keys(SCALAR_SPECS)) {
    if (!sections.has(key as DetailSection)) continue;
    const value = (draft.scalars[key] ?? "").trim();
    if (value) out[key] = value;
  }
  for (const [key, spec] of Object.entries(LIST_SPECS)) {
    if (!sections.has(key as DetailSection)) continue;
    const rows = (draft.rows[key] ?? [])
      .map((row) => rowToJson(row, spec.fields))
      .filter((row): row is Record<string, unknown> => row !== null);
    if (rows.length) out[key] = rows;
  }
  for (const [key, [maxLines]] of Object.entries(LINE_SPECS)) {
    if (!sections.has(key as DetailSection)) continue;
    const lines = (draft.lines[key] ?? "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .slice(0, maxLines);
    if (lines.length) out[key] = lines;
  }
  if (sections.has("menu_sections")) {
    const menu = draft.menu
      .map((section) => {
        const items = section.items
          .filter((item) => item.name.trim())
          .map((item) => {
            const entry: Record<string, unknown> = { name: item.name.trim() };
            if (item.description.trim()) entry.description = item.description.trim();
            const ngwee = kwachaToNgwee(item.price);
            if (ngwee !== null) entry.price_ngwee = ngwee;
            const dietary = item.dietary
              .split(",")
              .map((tag) => tag.trim())
              .filter(Boolean);
            if (dietary.length) entry.dietary = dietary;
            return entry;
          });
        return section.title.trim() && items.length ? { title: section.title.trim(), items } : null;
      })
      .filter((section) => section !== null);
    if (menu.length) out.menu_sections = menu;
  }
  if (sections.has("presented_by")) {
    const presented = rowToJson(draft.presentedBy, SPONSOR_FIELDS);
    if (presented) out.presented_by = presented;
  }
  return out;
}

export type DraftError =
  "requiredField" | "invalidTime" | "invalidUrl" | "invalidPrice" | "invalidNumber" | "tooMany";

function isHttps(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && Boolean(url.hostname);
  } catch {
    return false;
  }
}

function isImageRef(value: string): boolean {
  if (/^https?:\/\//i.test(value)) return isHttps(value);
  return /^[A-Za-z0-9][A-Za-z0-9/_\-.]*$/.test(value) && !value.includes("..");
}

function checkRow(row: Row, fields: FieldSpec[]): DraftError | null {
  const touched = fields.some((f) => (row[f.key] ?? "").trim());
  if (!touched) return null;
  for (const field of fields) {
    const value = (row[field.key] ?? "").trim();
    if (field.required && !value) return "requiredField";
    if (!value) continue;
    if (field.kind === "time" && !/^([01]\d|2[0-3]):[0-5]\d$/.test(value)) return "invalidTime";
    if (field.kind === "number" && !/^\d{1,3}$/.test(value)) return "invalidNumber";
    if (field.key === "link_url" && !isHttps(value)) return "invalidUrl";
    if ((field.key === "logo" || field.key === "image") && !isImageRef(value)) return "invalidUrl";
  }
  return null;
}

/** Client-side mirror of the API rules, so organisers see the problem before saving. */
export function validateDraft(archetype: EventArchetype, draft: DetailsDraft): DraftError | null {
  const sections = new Set<DetailSection>(ARCHETYPE_SECTIONS[archetype]);
  for (const key of ["doors_open"] as const) {
    const value = (draft.scalars[key] ?? "").trim();
    if (sections.has(key) && value && !/^([01]\d|2[0-3]):[0-5]\d$/.test(value))
      return "invalidTime";
  }
  const live = (draft.scalars.livestream_url ?? "").trim();
  if (sections.has("livestream_url") && live && !isHttps(live)) return "invalidUrl";
  for (const [key, spec] of Object.entries(LIST_SPECS)) {
    if (!sections.has(key as DetailSection)) continue;
    const rows = draft.rows[key] ?? [];
    const filled = rows.filter((row) => spec.fields.some((f) => (row[f.key] ?? "").trim()));
    if (filled.length > spec.max) return "tooMany";
    for (const row of rows) {
      const error = checkRow(row, spec.fields);
      if (error) return error;
    }
  }
  if (sections.has("presented_by")) {
    const error = checkRow(draft.presentedBy, SPONSOR_FIELDS);
    if (error) return error;
  }
  if (sections.has("menu_sections")) {
    if (draft.menu.length > MENU_LIMITS.sections) return "tooMany";
    for (const section of draft.menu) {
      if (section.items.length > MENU_LIMITS.items) return "tooMany";
      if (section.items.some((i) => i.name.trim()) && !section.title.trim()) return "requiredField";
      for (const item of section.items) {
        if (item.price.trim() && kwachaToNgwee(item.price) === null) return "invalidPrice";
      }
    }
  }
  return null;
}
