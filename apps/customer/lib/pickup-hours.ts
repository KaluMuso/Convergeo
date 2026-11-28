const DAY_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

// 2024-01-01 is a Monday; offsets give each weekday for Intl formatting.
const DAY_REFERENCE_UTC: Record<(typeof DAY_ORDER)[number], number> = {
  mon: Date.UTC(2024, 0, 1),
  tue: Date.UTC(2024, 0, 2),
  wed: Date.UTC(2024, 0, 3),
  thu: Date.UTC(2024, 0, 4),
  fri: Date.UTC(2024, 0, 5),
  sat: Date.UTC(2024, 0, 6),
  sun: Date.UTC(2024, 0, 7),
};

export function dayLabel(day: string, locale: string): string {
  const key = day.trim().toLowerCase() as (typeof DAY_ORDER)[number];
  const reference = DAY_REFERENCE_UTC[key];
  if (reference === undefined) {
    return day;
  }
  try {
    return new Intl.DateTimeFormat(locale, { weekday: "short", timeZone: "UTC" }).format(
      new Date(reference),
    );
  } catch {
    return day;
  }
}

function span(value: unknown): string | null {
  if (typeof value === "string") {
    return value.trim() || null;
  }
  if (Array.isArray(value)) {
    const parts = value.map(span).filter((part): part is string => part !== null);
    return parts.length > 0 ? parts.join(", ") : null;
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const open = typeof record.open === "string" ? record.open : null;
    const close = typeof record.close === "string" ? record.close : null;
    if (open && close) {
      return `${open}–${close}`;
    }
  }
  return null;
}

/** One day's hours as text ("08:00–17:00", the closed label, or null when unusable). */
export function formatDayHours(value: unknown, closedLabel: string): string | null {
  const isClosed =
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    (value as Record<string, unknown>).closed === true;
  return isClosed ? closedLabel : span(value);
}

/** Sort `[day, value]` hours entries Monday-first; unknown keys go last. */
export function sortHoursEntries<T>(entries: Array<[string, T]>): Array<[string, T]> {
  const rank = (day: string) => {
    const index = DAY_ORDER.indexOf(day.trim().toLowerCase() as (typeof DAY_ORDER)[number]);
    return index === -1 ? 99 : index;
  };
  return [...entries].sort(([a], [b]) => rank(a) - rank(b));
}

/**
 * Renders a vendor/branch `hours` map ({ mon: { open, close, closed } }) as
 * "Mon 08:00–17:00, Tue Closed". Never stringifies an object ("[object Object]").
 * `closedLabel` is a translated string.
 */
export function formatPickupHours(
  hours: Record<string, unknown> | null | undefined,
  locale: string,
  closedLabel: string,
): string {
  const entries = Object.entries(hours ?? {}).sort(([a], [b]) => {
    const ia = DAY_ORDER.indexOf(a.trim().toLowerCase() as (typeof DAY_ORDER)[number]);
    const ib = DAY_ORDER.indexOf(b.trim().toLowerCase() as (typeof DAY_ORDER)[number]);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });
  const parts: string[] = [];
  for (const [day, value] of entries) {
    const isClosed =
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      (value as Record<string, unknown>).closed === true;
    const text = isClosed ? closedLabel : span(value);
    if (text) {
      parts.push(`${dayLabel(day, locale)} ${text}`);
    }
  }
  return parts.length > 0 ? parts.join(", ") : "—";
}
