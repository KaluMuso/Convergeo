/**
 * Daily dispatch cut-off for the Lusaka pilot (manual dispatch, D-guardrails).
 *
 * Orders that are confirmed, packed and handed to the rider before 14:00
 * Lusaka time go out with today's riders; anything later goes out on the next
 * dispatch run. Zambia (CAT) is UTC+2 all year — no daylight saving — so a fixed
 * offset is exact and avoids shipping Intl time-zone data to 3G phones.
 *
 * Pure + deterministic (pass `now`) so the copy and badges are testable.
 */
export const DISPATCH_CUTOFF_HOUR = 14;
export const LUSAKA_UTC_OFFSET_MINUTES = 120;
/** Under this many minutes left the banner turns urgent. */
export const CUTOFF_URGENT_MINUTES = 60;

const MINUTES_PER_DAY = 24 * 60;

export type DispatchCutoffState =
  | { phase: "before"; minutesLeft: number; hours: number; minutes: number; urgent: boolean }
  | { phase: "after" };

export function lusakaMinutesOfDay(now: Date): number {
  const utcMinutes = now.getUTCHours() * 60 + now.getUTCMinutes();
  return (utcMinutes + LUSAKA_UTC_OFFSET_MINUTES) % MINUTES_PER_DAY;
}

export function dispatchCutoffState(now: Date = new Date()): DispatchCutoffState {
  const cutoff = DISPATCH_CUTOFF_HOUR * 60;
  const current = lusakaMinutesOfDay(now);
  if (current >= cutoff) {
    return { phase: "after" };
  }
  const minutesLeft = cutoff - current;
  return {
    phase: "before",
    minutesLeft,
    hours: Math.floor(minutesLeft / 60),
    minutes: minutesLeft % 60,
    urgent: minutesLeft <= CUTOFF_URGENT_MINUTES,
  };
}
