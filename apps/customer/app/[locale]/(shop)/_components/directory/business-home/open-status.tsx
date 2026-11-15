"use client";

import { useEffect, useState } from "react";

export type DaySchedule = {
  day: "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
  opens: string;
  closes: string;
};

const DAY_KEYS: DaySchedule["day"][] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

function minutes(value: string): number {
  const [h, m] = value.split(":").map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
}

/** Lusaka wall clock (UTC+2, no DST) — mirrors services/vendors/hours.py. */
function lusakaNow(at: Date): { dayIndex: number; minute: number } {
  const shifted = new Date(at.getTime() + 2 * 60 * 60 * 1000);
  // getUTCDay: 0 = Sunday → convert to Monday-first index.
  const dayIndex = (shifted.getUTCDay() + 6) % 7;
  return {
    dayIndex,
    minute: shifted.getUTCHours() * 60 + shifted.getUTCMinutes(),
  };
}

/**
 * Same rules as the API's `is_open_at`: overnight spans run into the next day,
 * zero-length windows are closed, and missing days are closed (fail closed).
 */
export function isOpenAt(schedule: DaySchedule[], at: Date): boolean {
  const { dayIndex, minute } = lusakaNow(at);
  const spanFor = (index: number) => schedule.find((entry) => entry.day === DAY_KEYS[index]);

  const today = spanFor(dayIndex);
  if (today) {
    const opens = minutes(today.opens);
    const closes = minutes(today.closes);
    if (opens < closes && minute >= opens && minute < closes) {
      return true;
    }
    if (opens > closes && minute >= opens) {
      return true;
    }
  }
  const yesterday = spanFor((dayIndex + 6) % 7);
  if (yesterday) {
    const opens = minutes(yesterday.opens);
    const closes = minutes(yesterday.closes);
    if (opens > closes && minute < closes) {
      return true;
    }
  }
  return false;
}

/**
 * "Open now" / "Closed now" for a cached (ISR) page: evaluated after mount so a
 * page cached an hour ago never shows a stale status, and nothing renders on
 * the server (no hydration mismatch, nothing wrong in the crawler's copy).
 */
export function OpenStatus({
  schedule,
  labels,
}: {
  schedule: DaySchedule[];
  labels: { open: string; closed: string };
}) {
  const [open, setOpen] = useState<boolean | null>(null);

  useEffect(() => {
    if (schedule.length === 0) {
      return;
    }
    setOpen(isOpenAt(schedule, new Date()));
  }, [schedule]);

  if (open === null) {
    return null;
  }
  return (
    <span
      data-testid="open-status"
      className={`inline-flex items-center gap-1.5 rounded-pill px-2.5 py-0.5 text-sm font-semibold ${
        open
          ? "border border-success bg-surface text-success"
          : "border border-border bg-bg-2 text-text-2"
      }`}
    >
      <span aria-hidden className={`h-2 w-2 rounded-full ${open ? "bg-success" : "bg-text-3"}`} />
      {open ? labels.open : labels.closed}
    </span>
  );
}
