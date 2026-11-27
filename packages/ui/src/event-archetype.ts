/**
 * Event archetypes (presentation templates) shared by the customer and vendor apps.
 *
 * Mirrors `services/api/app/services/events/archetypes.py` (the API validates and is
 * the source of truth; this module only derives, sanitises defensively and themes).
 * Presentation only: nothing here may influence payments, holds or tickets.
 * Spec: docs/plan/event-type-templates.md. Plain module, deliberately not "use client".
 */

export const EVENT_ARCHETYPES = [
  "concert",
  "religious",
  "sports_family",
  "restaurant",
  "private_gathering",
  "generic",
] as const;

export type EventArchetype = (typeof EVENT_ARCHETYPES)[number];

export function isEventArchetype(value: unknown): value is EventArchetype {
  return typeof value === "string" && (EVENT_ARCHETYPES as readonly string[]).includes(value);
}

export const CATEGORY_ARCHETYPE: Readonly<Record<string, EventArchetype>> = {
  music: "concert",
  concerts: "concert",
  festivals: "concert",
  gospel: "religious",
  nightlife: "concert",
  "comedy-theatre-parent": "concert",
  "comedy-theatre": "concert",
  "stand-up": "concert",
  religious: "religious",
  church: "religious",
  sports: "sports_family",
  football: "sports_family",
  family: "sports_family",
  "pop-up-dinners": "restaurant",
  "private-events": "private_gathering",
};

export function deriveArchetype(
  categorySlug: string | null | undefined,
  eventType?: string | null,
): EventArchetype {
  if (categorySlug && CATEGORY_ARCHETYPE[categorySlug]) return CATEGORY_ARCHETYPE[categorySlug];
  if (eventType === "private") return "private_gathering";
  return "generic";
}

/** Existing tokens only (spec rule A-4): never add a hex value here. */
export type ArchetypeTheme = {
  /** CSS colour expression for tinted surfaces. */
  tint: string;
  /** CSS colour expression for borders, kickers and highlights. */
  accent: string;
  /** Hero overlay: `panel` = dark stage, `soft` = light wash. */
  hero: "panel" | "soft";
};

export const ARCHETYPE_THEME: Readonly<Record<EventArchetype, ArchetypeTheme>> = {
  concert: {
    tint: "color-mix(in srgb, var(--accent) 16%, var(--surface))",
    accent: "var(--accent)",
    hero: "panel",
  },
  religious: {
    tint: "color-mix(in srgb, var(--cat-health) 22%, var(--surface))",
    accent: "var(--cat-health)",
    hero: "soft",
  },
  sports_family: {
    tint: "color-mix(in srgb, var(--cat-fitness) 22%, var(--surface))",
    accent: "var(--cat-fitness)",
    hero: "soft",
  },
  restaurant: {
    tint: "color-mix(in srgb, var(--cat-food) 22%, var(--surface))",
    accent: "var(--cat-food)",
    hero: "soft",
  },
  private_gathering: {
    tint: "color-mix(in srgb, var(--cat-beauty) 24%, var(--surface))",
    accent: "var(--cat-beauty)",
    hero: "soft",
  },
  generic: {
    tint: "var(--primary-tint)",
    accent: "var(--primary)",
    hero: "panel",
  },
};

// ---------------------------------------------------------------------------
// Details (loose, defensively sanitised view of the API's validated JSON)
// ---------------------------------------------------------------------------

export type Sponsor = {
  name: string;
  logo?: string;
  link_url?: string;
  tagline?: string;
  status: "pending" | "approved" | "rejected";
};
export type AgendaItem = {
  time: string;
  title: string;
  speaker?: string;
  notes?: string;
};
export type Person = {
  name: string;
  role?: string;
  image?: string;
  bio?: string;
};
export type LineupAct = {
  name: string;
  role: "headliner" | "support" | "dj" | "mc" | "guest";
  stage?: string;
  slot?: string;
  image?: string;
  bio?: string;
};
export type Activity = {
  name: string;
  age_group?: string;
  time?: string;
  area?: string;
};
export type AgeGroup = { label: string; min_age: number; max_age?: number };
export type MenuItem = {
  name: string;
  description?: string;
  price_ngwee?: number;
  dietary: string[];
};
export type MenuSection = { title: string; items: MenuItem[] };
export type Faq = { question: string; answer: string };
export type AgePolicy = "all_ages" | "guardian_under_12" | "16_plus" | "18_plus";

export type ArchetypeDetails = {
  sponsors: Sponsor[];
  dress_code?: string;
  age_policy?: AgePolicy;
  faqs: Faq[];
  lineup: LineupAct[];
  stages: string[];
  doors_open?: string;
  merch_note?: string;
  agenda: AgendaItem[];
  speakers: Person[];
  denomination?: string;
  donation_note?: string;
  livestream_url?: string;
  languages: string[];
  activities: Activity[];
  age_groups: AgeGroup[];
  bring_list: string[];
  family_bundle_note?: string;
  menu_sections: MenuSection[];
  seating_note?: string;
  reservation_note?: string;
  host_name?: string;
  host_names?: string;
  occasion?: string;
  rsvp_note?: string;
  gift_note?: string;
};

const AGE_POLICIES: readonly AgePolicy[] = ["all_ages", "guardian_under_12", "16_plus", "18_plus"];
const LINEUP_ROLES = ["headliner", "support", "dj", "mc", "guest"] as const;

type Rec = Record<string, unknown>;

function rec(value: unknown): Rec | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Rec)
    : null;
}

function str(value: unknown, max = 500): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed ? trimmed.slice(0, max) : undefined;
}

/** https only (rejects javascript:, data:, http:, relative). */
export function safeHttpsUrl(value: unknown): string | undefined {
  const text = str(value, 300);
  if (!text) return undefined;
  try {
    const url = new URL(text);
    return url.protocol === "https:" && url.hostname ? url.toString() : undefined;
  } catch {
    return undefined;
  }
}

/** Cloudinary public id or https URL; anything else (data:, ../) is dropped. */
export function safeImageRef(value: unknown): string | undefined {
  const text = str(value, 300);
  if (!text) return undefined;
  if (/^https?:\/\//i.test(text)) return safeHttpsUrl(text);
  return /^[A-Za-z0-9][A-Za-z0-9/_\-.]*$/.test(text) && !text.includes("..") ? text : undefined;
}

function time(value: unknown): string | undefined {
  const text = str(value, 5);
  return text && /^([01]\d|2[0-3]):[0-5]\d$/.test(text) ? text : undefined;
}

function list<T>(value: unknown, max: number, map: (item: unknown) => T | null): T[] {
  if (!Array.isArray(value)) return [];
  const out: T[] = [];
  for (const item of value) {
    const mapped = map(item);
    if (mapped !== null) out.push(mapped);
    if (out.length >= max) break;
  }
  return out;
}

function sponsor(value: unknown): Sponsor | null {
  const r = rec(value);
  const name = r && str(r.name, 80);
  if (!r || !name) return null;
  return {
    name,
    logo: safeImageRef(r.logo),
    link_url: safeHttpsUrl(r.link_url),
    tagline: str(r.tagline, 120),
    status: r.status === "approved" || r.status === "rejected" ? r.status : "pending",
  };
}

function person(value: unknown): Person | null {
  const r = rec(value);
  const name = r && str(r.name, 80);
  if (!r || !name) return null;
  return {
    name,
    role: str(r.role, 60),
    image: safeImageRef(r.image),
    bio: str(r.bio, 200),
  };
}

function agendaItem(value: unknown): AgendaItem | null {
  const r = rec(value);
  const at = r && time(r.time);
  const title = r && str(r.title, 200);
  if (!r || !at || !title) return null;
  return {
    time: at,
    title,
    speaker: str(r.speaker, 80),
    notes: str(r.notes, 300),
  };
}

function strings(value: unknown, max: number, len: number): string[] {
  return list(value, max, (item) => str(item, len) ?? null);
}

/** Defensive normaliser: unknown input in, render-safe typed details out. */
export function sanitiseDetails(raw: unknown): ArchetypeDetails {
  const r = rec(raw) ?? {};
  const agePolicy = AGE_POLICIES.find((p) => p === r.age_policy);
  return {
    sponsors: list(r.sponsors, 6, sponsor),
    dress_code: str(r.dress_code, 80),
    age_policy: agePolicy,
    faqs: list(r.faqs, 8, (item) => {
      const f = rec(item);
      const question = f && str(f.question, 120);
      const answer = f && str(f.answer, 500);
      return question && answer ? { question, answer } : null;
    }),
    lineup: list(r.lineup, 30, (item) => {
      const a = rec(item);
      const name = a && str(a.name, 80);
      if (!a || !name) return null;
      const role = LINEUP_ROLES.find((x) => x === a.role) ?? "support";
      return {
        name,
        role,
        stage: str(a.stage, 60),
        slot: time(a.slot),
        image: safeImageRef(a.image),
        bio: str(a.bio, 200),
      };
    }),
    stages: strings(r.stages, 6, 60),
    doors_open: time(r.doors_open),
    merch_note: str(r.merch_note, 200),
    agenda: list(r.agenda, 30, agendaItem),
    speakers: list(r.speakers, 12, person),
    denomination: str(r.denomination, 60),
    donation_note: str(r.donation_note, 300),
    livestream_url: safeHttpsUrl(r.livestream_url),
    languages: strings(r.languages, 4, 30),
    activities: list(r.activities, 20, (item) => {
      const a = rec(item);
      const name = a && str(a.name, 80);
      if (!a || !name) return null;
      return {
        name,
        age_group: str(a.age_group, 40),
        time: time(a.time),
        area: str(a.area, 60),
      };
    }),
    age_groups: list(r.age_groups, 8, (item) => {
      const g = rec(item);
      const label = g && str(g.label, 40);
      if (!g || !label || typeof g.min_age !== "number") return null;
      return {
        label,
        min_age: g.min_age,
        max_age: typeof g.max_age === "number" ? g.max_age : undefined,
      };
    }),
    bring_list: strings(r.bring_list, 10, 80),
    family_bundle_note: str(r.family_bundle_note, 300),
    menu_sections: list(r.menu_sections, 6, (item) => {
      const s = rec(item);
      const title = s && str(s.title, 80);
      if (!s || !title) return null;
      const items = list(s.items, 12, (entry) => {
        const m = rec(entry);
        const name = m && str(m.name, 80);
        if (!m || !name) return null;
        return {
          name,
          description: str(m.description, 160),
          price_ngwee:
            typeof m.price_ngwee === "number" && Number.isInteger(m.price_ngwee)
              ? m.price_ngwee
              : undefined,
          dietary: strings(m.dietary, 5, 20),
        };
      });
      return items.length ? { title, items } : null;
    }),
    seating_note: str(r.seating_note, 300),
    reservation_note: str(r.reservation_note, 300),
    host_name: str(r.host_name, 80),
    host_names: str(r.host_names, 120),
    occasion: str(r.occasion, 80),
    rsvp_note: str(r.rsvp_note, 300),
    gift_note: str(r.gift_note, 300),
  };
}

// ---------------------------------------------------------------------------
// Ticket tier classification (existing ticket-type data only)
// ---------------------------------------------------------------------------

export type TicketTierKind =
  "vvip" | "vip" | "ga" | "family" | "child" | "table" | "free" | "standard";

/** Deterministic name classifier used for badges; never affects price or checkout. */
export function classifyTicketTier(input: { name: string; isFree: boolean }): TicketTierKind {
  const name = input.name.toLowerCase();
  if (/\bvvip\b/.test(name)) return "vvip";
  if (/\bvip\b/.test(name)) return "vip";
  if (/\b(family|group|bundle)\b/.test(name)) return "family";
  if (/\b(child|children|kid|kids|junior|under\s?\d+)\b/.test(name)) return "child";
  if (/\b(table|seat|booth)\b/.test(name)) return "table";
  if (/\b(ga|general)\b/.test(name)) return "ga";
  if (input.isFree) return "free";
  return "standard";
}

// ---------------------------------------------------------------------------
// Which optional content sections each archetype offers (vendor form + layouts)
// ---------------------------------------------------------------------------

export type DetailSection =
  | "sponsors"
  | "dress_code"
  | "age_policy"
  | "faqs"
  | "lineup"
  | "stages"
  | "doors_open"
  | "merch_note"
  | "agenda"
  | "speakers"
  | "denomination"
  | "donation_note"
  | "livestream_url"
  | "languages"
  | "activities"
  | "age_groups"
  | "bring_list"
  | "family_bundle_note"
  | "menu_sections"
  | "seating_note"
  | "reservation_note"
  | "host_name"
  | "host_names"
  | "occasion"
  | "rsvp_note"
  | "gift_note";

const COMMON_SECTIONS: DetailSection[] = ["sponsors", "dress_code", "age_policy", "faqs"];

export const ARCHETYPE_SECTIONS: Readonly<Record<EventArchetype, readonly DetailSection[]>> = {
  concert: ["lineup", "stages", "doors_open", "merch_note", ...COMMON_SECTIONS],
  religious: [
    "agenda",
    "speakers",
    "denomination",
    "donation_note",
    "livestream_url",
    "languages",
    ...COMMON_SECTIONS,
  ],
  sports_family: [
    "activities",
    "age_groups",
    "bring_list",
    "family_bundle_note",
    ...COMMON_SECTIONS,
  ],
  restaurant: [
    "menu_sections",
    "seating_note",
    "reservation_note",
    "host_name",
    ...COMMON_SECTIONS,
  ],
  private_gathering: [
    "host_names",
    "occasion",
    "rsvp_note",
    "agenda",
    "gift_note",
    ...COMMON_SECTIONS,
  ],
  generic: ["agenda", ...COMMON_SECTIONS],
};
