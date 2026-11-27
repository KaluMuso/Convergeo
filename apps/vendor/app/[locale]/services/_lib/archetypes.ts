import { zmwDecimalToNgwee } from "../../listings/new/_lib/money";

/**
 * Service archetypes for the vendor app (docs/plan/service-type-templates.md). The field
 * definitions below mirror the API's per-archetype Pydantic models
 * (`services/api/app/schemas/service_archetypes.py`); the API stays the gate.
 */
export const ARCHETYPES = [
  "accommodation",
  "appointment",
  "membership",
  "on_site",
  "rental",
  "ticketed",
  "professional",
] as const;
export type Archetype = (typeof ARCHETYPES)[number];

export const VERTICAL_ARCHETYPE: Record<string, Archetype> = {
  lodging: "accommodation",
  property: "accommodation",
  beauty: "appointment",
  tailoring: "appointment",
  auto: "appointment",
  fitness: "membership",
  cleaning: "on_site",
  "home-services": "on_site",
  rentals: "rental",
  "family-fun": "ticketed",
  "tech-services": "professional",
  "printing-creative": "professional",
  "food-catering": "professional",
  staffing: "professional",
};

export function deriveArchetype(category: string | null | undefined): Archetype {
  return VERTICAL_ARCHETYPE[category ?? ""] ?? "professional";
}

export function effectiveArchetype(
  override: string | null | undefined,
  category: string | null | undefined,
): Archetype {
  return (ARCHETYPES as readonly string[]).includes(override ?? "")
    ? (override as Archetype)
    : deriveArchetype(category);
}

export type Row = Record<string, string>;
export type FieldValue = string | boolean | Row[];
export type FieldValues = Record<string, FieldValue>;

type Base = { key: string };
export type FieldDef =
  | (Base & { kind: "select"; options: readonly string[] })
  | (Base & { kind: "int"; min: number; max: number; step?: number })
  | (Base & { kind: "bool" })
  | (Base & { kind: "text"; max: number; time?: boolean })
  | (Base & { kind: "tags"; maxItems: number })
  | (Base & { kind: "money" })
  | (Base & { kind: "image" })
  | (Base & { kind: "rows"; maxRows: number; columns: readonly FieldDef[] });

const sel = (key: string, options: readonly string[]): FieldDef => ({
  key,
  kind: "select",
  options,
});
const int = (key: string, min: number, max: number, step?: number): FieldDef => ({
  key,
  kind: "int",
  min,
  max,
  step,
});
const bool = (key: string): FieldDef => ({ key, kind: "bool" });
const text = (key: string, max: number, time = false): FieldDef => ({
  key,
  kind: "text",
  max,
  time,
});
const tags = (key: string, maxItems: number): FieldDef => ({ key, kind: "tags", maxItems });
const IMAGE: FieldDef = { key: "image", kind: "image" };

export const OFFER_FIELDS: Record<Archetype, readonly FieldDef[]> = {
  accommodation: [
    sel("room_type", ["standard", "premium", "presidential", "family", "dorm", "other"]),
    sel("stay_kind", ["nightly", "monthly"]),
    int("sleeps", 1, 20),
    int("beds", 1, 10),
    sel("bed_type", ["single", "double", "queen", "king", "bunk"]),
    int("size_sqm", 5, 2000),
    tags("amenities", 10),
    bool("breakfast_included"),
    int("min_nights", 1, 30),
    int("units_available", 0, 500),
    IMAGE,
  ],
  appointment: [
    int("duration_min", 5, 480, 5),
    text("group", 40),
    tags("staff", 6),
    bool("home_visit"),
    bool("price_is_from"),
    IMAGE,
  ],
  membership: [
    sel("pass_kind", ["day", "week", "month", "quarter", "year", "class_pack"]),
    int("valid_days", 1, 730),
    int("visits_included", 1, 1000),
    bool("classes_included"),
    int("guest_passes", 0, 10),
    bool("peak_hours_only"),
  ],
  on_site: [
    sel("pricing_unit", ["hour", "visit", "room"]),
    int("min_hours", 1, 12),
    sel("home_size", ["studio", "one_two_bed", "three_bed", "four_plus"]),
    int("crew_size", 1, 10),
    bool("supplies_included"),
  ],
  rental: [
    sel("unit", ["hour", "day", "week"]),
    { key: "deposit_ngwee", kind: "money" },
    int("quantity_available", 0, 500),
    {
      key: "specs",
      kind: "rows",
      maxRows: 8,
      columns: [text("label", 40), text("value", 60)],
    },
    bool("with_operator"),
    bool("delivery_available"),
    int("min_period", 1, 30),
    IMAGE,
  ],
  ticketed: [
    sel("ticket_kind", ["adult", "child", "toddler", "senior", "family", "group"]),
    int("age_min", 0, 120),
    int("age_max", 0, 120),
    int("party_size", 1, 20),
    sel("entry", ["any_time", "timed"]),
    int("slot_capacity", 1, 5000),
  ],
  professional: [
    sel("rate_unit", ["hour", "day", "month", "project"]),
    text("role", 40),
    int("experience_years", 0, 50),
    sel("availability", ["now", "week", "booked"]),
    tags("certifications", 5),
  ],
};

const COMMON_SERVICE: readonly FieldDef[] = [
  sel("availability", ["available", "limited", "unavailable"]),
  tags("amenities", 12),
  sel("policy.cancellation", ["flexible", "moderate", "strict"]),
  text("policy.note", 200),
];

export const SERVICE_FIELDS: Record<Archetype, readonly FieldDef[]> = {
  accommodation: [...COMMON_SERVICE, text("check_in", 5, true), text("check_out", 5, true)],
  appointment: [
    ...COMMON_SERVICE,
    bool("walk_ins"),
    {
      key: "staff",
      kind: "rows",
      maxRows: 10,
      columns: [text("name", 40), text("role", 40)],
    },
  ],
  membership: [
    ...COMMON_SERVICE,
    {
      key: "class_schedule",
      kind: "rows",
      maxRows: 21,
      columns: [
        sel("day", ["0", "1", "2", "3", "4", "5", "6"]),
        text("start", 5, true),
        text("title", 40),
        int("duration_min", 5, 480),
        int("capacity", 1, 500),
      ],
    },
  ],
  on_site: COMMON_SERVICE,
  rental: [...COMMON_SERVICE, text("pickup_note", 200)],
  ticketed: [...COMMON_SERVICE, text("age_policy", 200)],
  professional: COMMON_SERVICE,
};

/** Per-archetype offer form behaviour. */
export const OFFER_META: Record<
  Archetype,
  { showDelivery: boolean; showRevisions: boolean; priceUnit: string }
> = {
  accommodation: { showDelivery: false, showRevisions: false, priceUnit: "night" },
  appointment: { showDelivery: false, showRevisions: false, priceUnit: "session" },
  membership: { showDelivery: false, showRevisions: false, priceUnit: "pass" },
  on_site: { showDelivery: false, showRevisions: false, priceUnit: "visit" },
  rental: { showDelivery: false, showRevisions: false, priceUnit: "period" },
  ticketed: { showDelivery: false, showRevisions: false, priceUnit: "ticket" },
  professional: { showDelivery: true, showRevisions: true, priceUnit: "package" },
};

// ---------------------------------------------------------------- nested key helpers
function getPath(source: Record<string, unknown>, key: string): unknown {
  const [head, tail] = key.split(".");
  if (!tail) return source[head as string];
  const inner = source[head as string];
  return inner && typeof inner === "object" ? (inner as Record<string, unknown>)[tail] : undefined;
}

function setPath(target: Record<string, unknown>, key: string, value: unknown): void {
  const [head, tail] = key.split(".");
  if (!tail) {
    target[head as string] = value;
    return;
  }
  const inner = (target[head as string] ?? {}) as Record<string, unknown>;
  inner[tail] = value;
  target[head as string] = inner;
}

export function emptyValue(def: FieldDef): FieldValue {
  if (def.kind === "bool") return false;
  if (def.kind === "rows") return [];
  return "";
}

export function emptyValues(defs: readonly FieldDef[]): FieldValues {
  return Object.fromEntries(defs.map((def) => [def.key, emptyValue(def)]));
}

/** API attributes -> editable strings. Unknown or mistyped values become empty. */
export function valuesFromAttributes(
  defs: readonly FieldDef[],
  attrs: Record<string, unknown> | null | undefined,
  toZmw: (ngwee: number) => string,
): FieldValues {
  const source = attrs ?? {};
  const out: FieldValues = {};
  for (const def of defs) {
    const raw = getPath(source, def.key);
    switch (def.kind) {
      case "bool":
        out[def.key] = raw === true;
        break;
      case "tags":
        out[def.key] = Array.isArray(raw)
          ? raw.filter((x) => typeof x === "string").join(", ")
          : "";
        break;
      case "money":
        out[def.key] = typeof raw === "number" ? toZmw(raw) : "";
        break;
      case "rows":
        out[def.key] = Array.isArray(raw)
          ? raw
              .filter((r): r is Record<string, unknown> => !!r && typeof r === "object")
              .map((r) =>
                Object.fromEntries(
                  def.columns.map((c) => [c.key, r[c.key] === undefined ? "" : String(r[c.key])]),
                ),
              )
          : [];
        break;
      default:
        out[def.key] = typeof raw === "string" || typeof raw === "number" ? String(raw) : "";
    }
  }
  return out;
}

const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;
const WHOLE = /^\d+$/;

export type AttributeErrors = Record<string, string>;

function convert(
  def: FieldDef,
  value: FieldValue | undefined,
): { ok: true; value: unknown; empty: boolean } | { ok: false; error: string } {
  switch (def.kind) {
    case "bool":
      return { ok: true, value: value === true, empty: value !== true };
    case "select": {
      const v = typeof value === "string" ? value : "";
      if (v === "") return { ok: true, value: undefined, empty: true };
      if (!def.options.includes(v)) return { ok: false, error: "invalid" };
      return { ok: true, value: /^\d$/.test(v) && def.key === "day" ? Number(v) : v, empty: false };
    }
    case "int": {
      const v = (typeof value === "string" ? value : "").trim();
      if (v === "") return { ok: true, value: undefined, empty: true };
      const n = WHOLE.test(v) ? Number(v) : NaN;
      if (!Number.isInteger(n) || n < def.min || n > def.max) return { ok: false, error: "int" };
      if (def.step && n % def.step !== 0) return { ok: false, error: "step" };
      return { ok: true, value: n, empty: false };
    }
    case "text": {
      const v = (typeof value === "string" ? value : "").trim();
      if (v === "") return { ok: true, value: undefined, empty: true };
      if (v.length > def.max) return { ok: false, error: "tooLong" };
      if (def.time && !TIME.test(v)) return { ok: false, error: "time" };
      return { ok: true, value: v, empty: false };
    }
    case "tags": {
      const items = (typeof value === "string" ? value : "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      if (items.length === 0) return { ok: true, value: undefined, empty: true };
      if (items.length > def.maxItems || items.some((s) => s.length > 40)) {
        return { ok: false, error: "tags" };
      }
      return { ok: true, value: items, empty: false };
    }
    case "money": {
      const v = (typeof value === "string" ? value : "").trim();
      if (v === "") return { ok: true, value: undefined, empty: true };
      try {
        const n = zmwDecimalToNgwee(v);
        if (n <= 0) return { ok: false, error: "money" };
        return { ok: true, value: n, empty: false };
      } catch {
        return { ok: false, error: "money" };
      }
    }
    case "image": {
      const v = typeof value === "string" ? value : "";
      return v === ""
        ? { ok: true, value: undefined, empty: true }
        : { ok: true, value: v, empty: false };
    }
    case "rows": {
      const rows = Array.isArray(value) ? value : [];
      const out: Record<string, unknown>[] = [];
      for (const row of rows) {
        const converted: Record<string, unknown> = {};
        let any = false;
        for (const col of def.columns) {
          const c = convert(col, row[col.key]);
          if (!c.ok) return { ok: false, error: "rows" };
          if (!c.empty) {
            converted[col.key] = c.value;
            any = true;
          }
        }
        if (any) out.push(converted);
      }
      if (out.length > def.maxRows) return { ok: false, error: "rows" };
      // Row columns the API requires.
      for (const row of out) {
        const required = def.columns.filter((c) =>
          ["label", "value", "name", "title", "start", "day"].includes(c.key),
        );
        if (required.some((c) => row[c.key] === undefined)) return { ok: false, error: "rows" };
      }
      return out.length === 0
        ? { ok: true, value: undefined, empty: true }
        : { ok: true, value: out, empty: false };
    }
  }
}

/**
 * Editable values -> API attributes. Only keys defined for this archetype are sent (stale
 * keys from a previous archetype would be refused), and empty fields are omitted.
 */
export function attributesFromValues(
  defs: readonly FieldDef[],
  values: FieldValues,
): { ok: true; attributes: Record<string, unknown> } | { ok: false; errors: AttributeErrors } {
  const attributes: Record<string, unknown> = {};
  const errors: AttributeErrors = {};
  for (const def of defs) {
    const result = convert(def, values[def.key]);
    if (!result.ok) {
      errors[def.key] = result.error;
    } else if (!result.empty) {
      setPath(attributes, def.key, result.value);
    }
  }
  const ages = [attributes.age_min, attributes.age_max];
  if (typeof ages[0] === "number" && typeof ages[1] === "number" && ages[1] < ages[0]) {
    errors.age_max = "ageOrder";
  }
  return Object.keys(errors).length > 0 ? { ok: false, errors } : { ok: true, attributes };
}
