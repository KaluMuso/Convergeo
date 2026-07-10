"use client";

import { useTranslations } from "next-intl";

import { type TimelineEvent } from "./api";

type OrderTimelineProps = {
  events: TimelineEvent[];
  locale: string;
};

export function OrderTimeline({ events, locale }: OrderTimelineProps) {
  const t = useTranslations("admin.orders.timeline");

  if (events.length === 0) {
    return <p className="text-sm text-[#6B5E4C]">{t("empty")}</p>;
  }

  return (
    <ol className="space-y-3">
      {events.map((event) => (
        <li
          key={event.id}
          className="rounded-md border border-[#F0E9DE] bg-[#FAF7F2] px-3 py-2 text-sm"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium text-[#2A2118]">
              {t("statusChange", {
                from: event.from_status ?? t("missing"),
                to: event.to_status ?? t("missing"),
              })}
            </span>
            <time className="text-xs text-[#6B5E4C]">
              {new Date(event.created_at).toLocaleString(locale)}
            </time>
          </div>
          {event.note ? <p className="mt-1 text-[#6B5E4C]">{event.note}</p> : null}
        </li>
      ))}
    </ol>
  );
}
