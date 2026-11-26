"use client";

type DateFilterCalendarLabels = {
  calendarLabel: string;
};

type DateFilterCalendarProps = {
  labels: DateFilterCalendarLabels;
  days: Date[];
  eventDateSet: Set<string>;
  activeOnDate: string | null;
  isPending: boolean;
  lusakaIsoDate: (day: Date) => string;
  onSelectDate: (iso: string | null) => void;
};

/** Month grid — lazy-loaded from date-filter-chips to keep /events JS smaller. */
export function DateFilterCalendar({
  labels,
  days,
  eventDateSet,
  activeOnDate,
  isPending,
  lusakaIsoDate,
  onSelectDate,
}: DateFilterCalendarProps) {
  return (
    <details className="group rounded-lg border border-border bg-surface">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between px-3 text-sm font-semibold text-text-2">
        {labels.calendarLabel}
        <span aria-hidden className="transition-transform group-open:rotate-180">
          ⌄
        </span>
      </summary>
      <div className="px-3 pb-3">
        <div className="grid grid-cols-7 gap-1 text-center text-xs" role="group">
          {days.map((day) => {
            const iso = lusakaIsoDate(day);
            const hasEvent = eventDateSet.has(iso);
            const selected = activeOnDate === iso;
            return (
              <button
                key={iso}
                type="button"
                aria-pressed={selected}
                disabled={isPending}
                onClick={() => onSelectDate(selected ? null : iso)}
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
    </details>
  );
}
