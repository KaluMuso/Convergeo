"use client";

import { Button } from "@vergeo/ui/src/button";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useTransition } from "react";

export const EVENT_DATE_WINDOWS = ["tonight", "this_weekend", "all"] as const;
export const EVENT_CATEGORIES = [
  "workshops",
  "comedy-theatre",
  "pop-up-dinners",
  "cultural-arts",
  "lifestyle-community",
  "free-rsvp",
] as const;

export type EventDateWindow = "tonight" | "this_weekend" | "all";
export type EventCategory = (typeof EVENT_CATEGORIES)[number];

type DateFilterLabels = {
  tonight: string;
  thisWeekend: string;
  allDates: string;
  categoryLabel: string;
  calendarLabel: string;
  categories: {
    all: string;
  } & Record<EventCategory, string>;
};

type DateFilterChipsProps = {
  labels: DateFilterLabels;
  calendarDates: string[];
  activeDateWindow: EventDateWindow;
  activeCategory: EventCategory | null;
};

function monthDays(reference: Date): Date[] {
  const year = reference.getFullYear();
  const month = reference.getMonth();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  return Array.from({ length: daysInMonth }, (_, index) => new Date(year, month, index + 1));
}

export function DateFilterChips({
  labels,
  calendarDates,
  activeDateWindow,
  activeCategory,
}: DateFilterChipsProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const eventDateSet = useMemo(() => new Set(calendarDates), [calendarDates]);
  const monthReference = useMemo(() => new Date(), []);
  const days = useMemo(() => monthDays(monthReference), [monthReference]);

  const updateParams = useCallback(
    (updates: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value === null) {
          params.delete(key);
        } else {
          params.set(key, value);
        }
      }
      startTransition(() => {
        const query = params.toString();
        router.replace(query ? `${pathname}?${query}` : pathname);
      });
    },
    [pathname, router, searchParams],
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2" role="group" aria-label={labels.categoryLabel}>
        <Button
          type="button"
          variant={activeDateWindow === "tonight" ? "primary" : "secondary"}
          size="sm"
          disabled={isPending}
          loading={isPending}
          loadingLabel={labels.tonight}
          onClick={() => updateParams({ date_window: "tonight" })}
        >
          {labels.tonight}
        </Button>
        <Button
          type="button"
          variant={activeDateWindow === "this_weekend" ? "primary" : "secondary"}
          size="sm"
          disabled={isPending}
          loading={isPending}
          loadingLabel={labels.thisWeekend}
          onClick={() => updateParams({ date_window: "this_weekend" })}
        >
          {labels.thisWeekend}
        </Button>
        <Button
          type="button"
          variant={activeDateWindow === "all" ? "primary" : "secondary"}
          size="sm"
          disabled={isPending}
          loading={isPending}
          loadingLabel={labels.allDates}
          onClick={() => updateParams({ date_window: "all" })}
        >
          {labels.allDates}
        </Button>
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-sm font-semibold text-text-2">{labels.categoryLabel}</p>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant={activeCategory === null ? "primary" : "ghost"}
            size="sm"
            disabled={isPending}
            loading={isPending}
            loadingLabel={labels.categories.all}
            onClick={() => updateParams({ category: null })}
          >
            {labels.categories.all}
          </Button>
          {EVENT_CATEGORIES.map((category) => (
            <Button
              key={category}
              type="button"
              variant={activeCategory === category ? "primary" : "ghost"}
              size="sm"
              disabled={isPending}
              loading={isPending}
              loadingLabel={labels.categories[category] ?? category}
              onClick={() => updateParams({ category })}
            >
              {labels.categories[category] ?? category}
            </Button>
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-border bg-surface p-3">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-3">
          {labels.calendarLabel}
        </p>
        <div
          className="grid grid-cols-7 gap-1 text-center text-xs"
          aria-label={labels.calendarLabel}
        >
          {days.map((day) => {
            const iso = day.toISOString().slice(0, 10);
            const hasEvent = eventDateSet.has(iso);
            return (
              <div
                key={iso}
                className={`rounded-md px-1 py-2 ${
                  hasEvent ? "bg-primary/10 font-semibold text-primary" : "text-text-3"
                }`}
              >
                {day.getDate()}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
