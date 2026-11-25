const LUSAKA_TZ = "Africa/Lusaka";

function lusakaDateParts(date: Date): { y: number; m: number; d: number } {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: LUSAKA_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const pick = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? "0");
  return { y: pick("year"), m: pick("month"), d: pick("day") };
}

function calendarDayIndex(parts: { y: number; m: number; d: number }): number {
  return parts.y * 10_000 + parts.m * 100 + parts.d;
}

export type EventCountdownKind = "ended" | "today" | "tomorrow" | "days";

export type EventCountdownState =
  | { kind: "ended" }
  | { kind: "today"; timeLabel: string }
  | { kind: "tomorrow" }
  | { kind: "days"; days: number };

export function formatEventTimeLusaka(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    hour: "numeric",
    minute: "2-digit",
    timeZone: LUSAKA_TZ,
  }).format(new Date(iso));
}

/**
 * Server-side countdown copy state using the Lusaka calendar day (UTC+2).
 * No client timer — the label is fixed at render time.
 */
export function eventCountdownState(
  startsAtIso: string,
  endsAtMs: number,
  now: Date = new Date(),
  locale = "en",
): EventCountdownState | null {
  const startMs = new Date(startsAtIso).getTime();
  if (!Number.isFinite(startMs)) {
    return null;
  }
  if (Number.isFinite(endsAtMs) && endsAtMs < now.getTime()) {
    return { kind: "ended" };
  }
  if (startMs < now.getTime()) {
    return { kind: "ended" };
  }

  const startDay = calendarDayIndex(lusakaDateParts(new Date(startMs)));
  const todayDay = calendarDayIndex(lusakaDateParts(now));
  const dayDiff = startDay - todayDay;

  if (dayDiff <= 0) {
    return {
      kind: "today",
      timeLabel: formatEventTimeLusaka(startsAtIso, locale),
    };
  }
  if (dayDiff === 1) {
    return { kind: "tomorrow" };
  }
  return { kind: "days", days: dayDiff };
}
