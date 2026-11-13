/**
 * "Today" view — pure helpers (no React, no fetch) so the cut-off clock and the
 * count derivation are unit tested. Counts come only from existing admin list
 * endpoints; nothing here invents data.
 */

/** Lusaka is CAT (UTC+2) all year — Zambia has no daylight saving. */
const LUSAKA_OFFSET_HOURS = 2;
export const DISPATCH_CUTOFF_HOUR = 14;

export type CutoffClock = {
  /** True once today's 14:00 Lusaka cut-off has passed. */
  passed: boolean;
  /** Whole hours / minutes until the cut-off (0 when passed). */
  hours: number;
  minutes: number;
  /** Under an hour left: the UI escalates the tone. */
  urgent: boolean;
};

export function dispatchCutoffClock(now: Date): CutoffClock {
  const lusakaNow = new Date(now.getTime() + LUSAKA_OFFSET_HOURS * 3_600_000);
  const cutoffLusaka = Date.UTC(
    lusakaNow.getUTCFullYear(),
    lusakaNow.getUTCMonth(),
    lusakaNow.getUTCDate(),
    DISPATCH_CUTOFF_HOUR,
  );
  const remaining = cutoffLusaka - lusakaNow.getTime();
  if (remaining <= 0) {
    return { passed: true, hours: 0, minutes: 0, urgent: false };
  }
  const totalMinutes = Math.ceil(remaining / 60_000);
  return {
    passed: false,
    hours: Math.floor(totalMinutes / 60),
    minutes: totalMinutes % 60,
    urgent: totalMinutes <= 60,
  };
}

type WithSla = { sla_badge?: string | null };

export function countOverdue(items: readonly WithSla[]): number {
  return items.filter((item) => item.sla_badge === "overdue").length;
}

export type TodayTone = "clear" | "attention" | "urgent";

/** Zero is calm; any work is attention; overdue / past-cutoff escalates. */
export function toneFor(count: number, escalate: boolean): TodayTone {
  if (count <= 0) return "clear";
  return escalate ? "urgent" : "attention";
}
