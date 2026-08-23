"use client";

import { Button } from "@vergeo/ui/src/button";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState, useTransition } from "react";

import { EVENT_CATEGORIES, type EventCategory, type EventDateWindow } from "./event-taxonomy";

type DateFilterLabels = {
  tonight: string;
  thisWeekend: string;
  nextWeek: string;
  nextMonth: string;
  allDates: string;
  categoryLabel: string;
  calendarLabel: string;
  cityLabel: string;
  cityPlaceholder: string;
  neighbourhoodLabel: string;
  neighbourhoodPlaceholder: string;
  nearMe: string;
  nearMeDenied: string;
  categories: {
    all: string;
  } & Record<string, string>;
};

type DateFilterChipsProps = {
  labels: DateFilterLabels;
  calendarDates: string[];
  categories: string[];
  activeDateWindow: EventDateWindow;
  activeOnDate: string | null;
  activeCategory: EventCategory | null;
  activeCity: string;
  activeNeighbourhood: string;
  nearMeActive: boolean;
};

function monthDays(reference: Date): Date[] {
  const year = reference.getFullYear();
  const month = reference.getMonth();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  return Array.from({ length: daysInMonth }, (_, index) => new Date(year, month, index + 1));
}

function lusakaIsoDate(day: Date): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Africa/Lusaka",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(day);
  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  const date = parts.find((part) => part.type === "day")?.value;
  return `${year}-${month}-${date}`;
}

export function DateFilterChips({
  labels,
  calendarDates,
  categories,
  activeDateWindow,
  activeOnDate,
  activeCategory,
  activeCity,
  activeNeighbourhood,
  nearMeActive,
}: DateFilterChipsProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [cityDraft, setCityDraft] = useState(activeCity);
  const [neighbourhoodDraft, setNeighbourhoodDraft] = useState(activeNeighbourhood);
  const [geoDenied, setGeoDenied] = useState(false);

  const eventDateSet = useMemo(() => new Set(calendarDates), [calendarDates]);
  const monthReference = useMemo(() => new Date(), []);
  const days = useMemo(() => monthDays(monthReference), [monthReference]);
  const categoryChips = categories.length > 0 ? categories : [...EVENT_CATEGORIES];

  const updateParams = useCallback(
    (updates: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value === null || value === "") {
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

  const setDateWindow = (window: EventDateWindow) => {
    updateParams({
      date_window: window === "tonight" ? null : window,
      on_date: null,
    });
  };

  const requestNearMe = () => {
    if (!navigator.geolocation) {
      setGeoDenied(true);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setGeoDenied(false);
        updateParams({
          lat: String(position.coords.latitude),
          lng: String(position.coords.longitude),
        });
      },
      () => {
        setGeoDenied(true);
      },
      { enableHighAccuracy: false, timeout: 8_000, maximumAge: 60_000 },
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2" role="group" aria-label={labels.tonight}>
        <Button
          type="button"
          variant={activeDateWindow === "tonight" && !activeOnDate ? "primary" : "secondary"}
          size="sm"
          disabled={isPending}
          loading={isPending}
          loadingLabel={labels.tonight}
          onClick={() => setDateWindow("tonight")}
        >
          {labels.tonight}
        </Button>
        <Button
          type="button"
          variant={activeDateWindow === "this_weekend" && !activeOnDate ? "primary" : "secondary"}
          size="sm"
          disabled={isPending}
          loading={isPending}
          loadingLabel={labels.thisWeekend}
          onClick={() => setDateWindow("this_weekend")}
        >
          {labels.thisWeekend}
        </Button>
        <Button
          type="button"
          variant={activeDateWindow === "next_week" && !activeOnDate ? "primary" : "secondary"}
          size="sm"
          disabled={isPending}
          loading={isPending}
          loadingLabel={labels.nextWeek}
          onClick={() => setDateWindow("next_week")}
        >
          {labels.nextWeek}
        </Button>
        <Button
          type="button"
          variant={activeDateWindow === "next_month" && !activeOnDate ? "primary" : "secondary"}
          size="sm"
          disabled={isPending}
          loading={isPending}
          loadingLabel={labels.nextMonth}
          onClick={() => setDateWindow("next_month")}
        >
          {labels.nextMonth}
        </Button>
        <Button
          type="button"
          variant={activeDateWindow === "all" && !activeOnDate ? "primary" : "secondary"}
          size="sm"
          disabled={isPending}
          loading={isPending}
          loadingLabel={labels.allDates}
          onClick={() => setDateWindow("all")}
        >
          {labels.allDates}
        </Button>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <label className="flex min-w-0 flex-1 flex-col gap-1.5 text-sm">
          <span className="font-semibold text-text-2">{labels.cityLabel}</span>
          <input
            type="search"
            className="min-h-11 rounded-md border border-border bg-bg px-3 text-text"
            value={cityDraft}
            placeholder={labels.cityPlaceholder}
            onChange={(event) => setCityDraft(event.target.value)}
            onBlur={() => {
              if (cityDraft.trim() !== activeCity) {
                updateParams({ city: cityDraft.trim() || null });
              }
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                updateParams({ city: cityDraft.trim() || null });
              }
            }}
          />
        </label>
        <label className="flex min-w-0 flex-1 flex-col gap-1.5 text-sm">
          <span className="font-semibold text-text-2">{labels.neighbourhoodLabel}</span>
          <input
            type="search"
            className="min-h-11 rounded-md border border-border bg-bg px-3 text-text"
            value={neighbourhoodDraft}
            placeholder={labels.neighbourhoodPlaceholder}
            onChange={(event) => setNeighbourhoodDraft(event.target.value)}
            onBlur={() => {
              if (neighbourhoodDraft.trim() !== activeNeighbourhood) {
                updateParams({ neighbourhood: neighbourhoodDraft.trim() || null });
              }
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                updateParams({ neighbourhood: neighbourhoodDraft.trim() || null });
              }
            }}
          />
        </label>
        <Button
          type="button"
          variant={nearMeActive ? "primary" : "secondary"}
          size="sm"
          disabled={isPending}
          loading={isPending}
          loadingLabel={labels.nearMe}
          onClick={() => {
            if (nearMeActive) {
              updateParams({ lat: null, lng: null });
              return;
            }
            requestNearMe();
          }}
        >
          {labels.nearMe}
        </Button>
      </div>
      {geoDenied ? <p className="text-xs text-danger">{labels.nearMeDenied}</p> : null}

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
          {categoryChips.map((category) => (
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
          role="listbox"
        >
          {days.map((day) => {
            const iso = lusakaIsoDate(day);
            const hasEvent = eventDateSet.has(iso);
            const selected = activeOnDate === iso;
            return (
              <button
                key={iso}
                type="button"
                role="option"
                aria-selected={selected}
                disabled={isPending}
                onClick={() =>
                  updateParams({
                    on_date: selected ? null : iso,
                    date_window: null,
                  })
                }
                className={`min-h-11 rounded-md px-1 py-2 focus-visible:outline-none focus-visible:shadow-focusRing ${
                  selected
                    ? "bg-primary font-semibold text-[var(--primary-btn-fg)]"
                    : hasEvent
                      ? "bg-primary/10 font-semibold text-primary"
                      : "text-text-3"
                }`}
              >
                {day.getDate()}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
