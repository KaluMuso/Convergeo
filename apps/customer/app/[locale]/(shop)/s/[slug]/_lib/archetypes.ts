import { ICON_HUE_LIGHT, type IconHue } from "@vergeo/ui/src/icon-hues";

import type { CSSProperties } from "react";

/**
 * Service archetypes (docs/plan/service-type-templates.md): how a service is offered and
 * booked. The API sends the effective archetype; anything unknown falls back to the
 * generic `professional` layout so a bad value can never break the page (ST-7).
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

/** Archetypes with a bespoke layout in this release; the rest use the generic layout. */
export const BESPOKE_ARCHETYPES: readonly Archetype[] = [
  "accommodation",
  "appointment",
  "membership",
  "rental",
];

export function parseArchetype(value: unknown): Archetype {
  return typeof value === "string" && (ARCHETYPES as readonly string[]).includes(value)
    ? (value as Archetype)
    : "professional";
}

export function isBespoke(archetype: Archetype): boolean {
  return BESPOKE_ARCHETYPES.includes(archetype);
}

/** Vibe = one `packages/ui` icon hue per archetype; surfaces mix it into `--surface`. */
export const ARCHETYPE_HUE: Record<Archetype, IconHue> = {
  accommodation: "teal",
  appointment: "pink",
  membership: "orange",
  on_site: "green",
  rental: "amber",
  ticketed: "purple",
  professional: "blue",
};

/** CSS custom properties for a vibe; follow the theme because they mix into `--surface`. */
export function vibeStyle(archetype: Archetype): CSSProperties {
  const stroke = ICON_HUE_LIGHT[ARCHETYPE_HUE[archetype]].stroke;
  return {
    ["--vibe" as string]: stroke,
    ["--vibe-tint" as string]: `color-mix(in srgb, ${stroke} 12%, var(--surface))`,
    ["--vibe-strong" as string]: `color-mix(in srgb, ${stroke} 28%, var(--surface))`,
  };
}

export type Attributes = Record<string, unknown>;

export function asRecord(value: unknown): Attributes {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Attributes) : {};
}

export function attrNumber(attrs: Attributes, key: string): number | null {
  const value = attrs[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function attrString(attrs: Attributes, key: string): string | null {
  const value = attrs[key];
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

export function attrBool(attrs: Attributes, key: string): boolean {
  return attrs[key] === true;
}

export function attrStrings(attrs: Attributes, key: string): string[] {
  const value = attrs[key];
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.trim() !== "")
    : [];
}

export type Availability = "available" | "limited" | "unavailable";

export function parseAvailability(attrs: Attributes): Availability {
  const value = attrs.availability;
  return value === "limited" || value === "unavailable" ? value : "available";
}

export type ClassSlot = {
  day: number;
  start: string;
  title: string;
  duration_min: number;
  capacity: number | null;
};

/** Class schedule rows, sorted by day then time; invalid rows are dropped. */
export function parseSchedule(attrs: Attributes): ClassSlot[] {
  const raw = attrs.class_schedule;
  if (!Array.isArray(raw)) return [];
  const rows: ClassSlot[] = [];
  for (const item of raw) {
    const row = asRecord(item);
    const day = attrNumber(row, "day");
    const start = attrString(row, "start");
    const title = attrString(row, "title");
    if (day === null || day < 0 || day > 6 || !start || !title) continue;
    rows.push({
      day,
      start,
      title,
      duration_min: attrNumber(row, "duration_min") ?? 60,
      capacity: attrNumber(row, "capacity"),
    });
  }
  return rows.sort((a, b) => a.day - b.day || a.start.localeCompare(b.start));
}

export type StaffMember = { name: string; role: string | null };

export function parseStaff(attrs: Attributes): StaffMember[] {
  const raw = attrs.staff;
  if (!Array.isArray(raw)) return [];
  const out: StaffMember[] = [];
  for (const item of raw) {
    const row = asRecord(item);
    const name = attrString(row, "name");
    if (name) out.push({ name, role: attrString(row, "role") });
  }
  return out;
}
