import type { Archetype } from "./archetypes";

/**
 * The booking fields each archetype collects, and the localised request text built from
 * them. Requests are plain RFQ text plus the chosen `package_id` (SP-1: nothing is
 * reserved, nothing is paid). Pure functions, unit-tested.
 */
export type RequestFields = {
  /** ISO dates (yyyy-mm-dd) from `<input type="date">`. */
  startDate: string;
  endDate: string;
  /** "HH:MM", or a time-of-day key (morning | afternoon | evening | any). */
  time: string;
  guests: number;
  quantity: number;
  /** Rental period length in the offer's unit; membership ignores it. */
  period: number;
  staff: string;
};

export const EMPTY_FIELDS: RequestFields = {
  startDate: "",
  endDate: "",
  time: "any",
  guests: 2,
  quantity: 1,
  period: 1,
  staff: "",
};

export type RequestFieldKey =
  "startDate" | "endDate" | "time" | "guests" | "quantity" | "period" | "staff";

/** Which inputs the panel shows for an archetype. */
export const ARCHETYPE_FIELDS: Record<Archetype, readonly RequestFieldKey[]> = {
  accommodation: ["startDate", "endDate", "guests"],
  appointment: ["startDate", "time", "staff"],
  membership: ["startDate"],
  on_site: ["startDate", "time"],
  rental: ["startDate", "period", "quantity"],
  ticketed: ["startDate", "time", "guests"],
  professional: [],
};

export type RequestErrorKey = "pickOffer" | "pickDate" | "pickEnd" | "endBeforeStart" | "pastDate";

const DAY_MS = 24 * 60 * 60 * 1000;

function parseDay(value: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const ms = Date.parse(`${value}T00:00:00Z`);
  return Number.isNaN(ms) ? null : ms;
}

export function nightsBetween(start: string, end: string): number | null {
  const a = parseDay(start);
  const b = parseDay(end);
  if (a === null || b === null) return null;
  return Math.round((b - a) / DAY_MS);
}

/** Validation for the fields an archetype requires; `today` is an ISO date. */
export function validateRequest(
  archetype: Archetype,
  fields: RequestFields,
  opts: { hasOffers: boolean; offerSelected: boolean; today: string },
): RequestErrorKey | null {
  if (opts.hasOffers && !opts.offerSelected) return "pickOffer";
  const shown = ARCHETYPE_FIELDS[archetype];
  if (shown.includes("startDate")) {
    if (parseDay(fields.startDate) === null) return "pickDate";
    if (fields.startDate < opts.today) return "pastDate";
  }
  if (shown.includes("endDate")) {
    if (parseDay(fields.endDate) === null) return "pickEnd";
    if ((nightsBetween(fields.startDate, fields.endDate) ?? 0) < 1) return "endBeforeStart";
  }
  return null;
}

/** Plain data (no functions) so the same object can cross the server/client boundary. */
export type RequestTextLabels = {
  offer: string;
  startDate: Record<Archetype, string>;
  endDate: string;
  time: string;
  guests: string;
  quantity: string;
  period: string;
  staff: string;
  /** Templates with a `{count}` placeholder. */
  nightsOne: string;
  nightsMany: string;
  periods: Record<string, { one: string; many: string }>;
  timeOfDay: Record<string, string>;
};

export type RequestTextInput = {
  archetype: Archetype;
  fields: RequestFields;
  offerName: string | null;
  offerPrice: string | null;
  /** Rental unit of the chosen offer (hour | day | week). */
  unit: string;
  labels: RequestTextLabels;
};

function plural(count: number, one: string, many: string): string {
  return (count === 1 ? one : many).replace("{count}", String(count));
}

/** One `Label: value` line per filled field; stable order; empty values are skipped. */
export function buildRequestText(input: RequestTextInput): string {
  const { archetype, fields, labels } = input;
  const shown = ARCHETYPE_FIELDS[archetype];
  const lines: string[] = [];
  if (input.offerName) {
    lines.push(
      `${labels.offer}: ${input.offerName}${input.offerPrice ? ` (${input.offerPrice})` : ""}`,
    );
  }
  if (shown.includes("startDate") && fields.startDate) {
    lines.push(`${labels.startDate[archetype]}: ${fields.startDate}`);
  }
  if (shown.includes("endDate") && fields.endDate) {
    const nights = nightsBetween(fields.startDate, fields.endDate);
    lines.push(
      `${labels.endDate}: ${fields.endDate}${
        nights && nights > 0 ? ` (${plural(nights, labels.nightsOne, labels.nightsMany)})` : ""
      }`,
    );
  }
  if (shown.includes("time") && fields.time) {
    lines.push(`${labels.time}: ${labels.timeOfDay[fields.time] ?? fields.time}`);
  }
  if (shown.includes("staff") && fields.staff) {
    lines.push(`${labels.staff}: ${fields.staff}`);
  }
  if (shown.includes("guests")) lines.push(`${labels.guests}: ${Math.max(1, fields.guests)}`);
  if (shown.includes("period")) {
    const period = labels.periods[input.unit] ?? labels.periods.day;
    lines.push(
      `${labels.period}: ${period ? plural(Math.max(1, fields.period), period.one, period.many) : fields.period}`,
    );
  }
  if (shown.includes("quantity")) lines.push(`${labels.quantity}: ${Math.max(1, fields.quantity)}`);
  return lines.join("\n");
}
