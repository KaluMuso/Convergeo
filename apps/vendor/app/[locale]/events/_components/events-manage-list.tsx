"use client";

import { useSession } from "@vergeo/auth/use-session";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { createEventsClient, type EventSummary } from "../_lib/events-client";
import { Badge, Spinner } from "../_lib/ui";

type EventsManageListProps = {
  locale: string;
};

function statusBadgeVariant(
  status: EventSummary["status"],
): "new" | "free" | "sold_out" | "public" {
  if (status === "published") {
    return "free";
  }
  if (status === "draft") {
    return "new";
  }
  if (status === "completed") {
    return "public";
  }
  return "sold_out";
}

export function EventsManageList({ locale }: EventsManageListProps) {
  const t = useTranslations("vendor");
  const te = useTranslations("events");
  const { session, loading: sessionLoading } = useSession();
  const [items, setItems] = useState<EventSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const eventsClient = useMemo(() => createEventsClient(getToken), [getToken]);

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    eventsClient
      .listEvents()
      .then((response) => {
        if (!cancelled) {
          setItems(response.items);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(t("events.errors.loadFailed"));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [eventsClient, session, sessionLoading, t]);

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("events.list.loading")} />
      </div>
    );
  }

  if (!session) {
    return <p className="text-sm text-text-2">{t("events.errors.authRequired")}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="space-y-2">
        <p className="text-xs uppercase tracking-wide text-text-2">{t("events.eyebrow")}</p>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-text">{t("events.list.title")}</h1>
            <p className="text-sm text-text-2">{t("events.list.intro")}</p>
          </div>
          <Link
            href={`/${locale}/events/new`}
            className="inline-flex min-h-11 items-center rounded-md bg-primary px-3 text-sm font-medium text-surface"
          >
            {t("events.list.createCta")}
          </Link>
        </div>
      </header>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-6 text-center">
          <p className="text-sm text-text-2">{t("events.list.empty")}</p>
          <Link
            href={`/${locale}/events/new`}
            className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-primary"
          >
            {t("events.list.createCta")}
          </Link>
        </div>
      ) : (
        <ul className="space-y-3">
          {items.map((event) => (
            <li key={event.id} className="rounded-lg border border-border p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 space-y-1">
                  <p className="truncate font-medium text-text">{event.title}</p>
                  <p className="text-xs text-text-2">
                    {event.venue ?? t("events.list.noVenue")}
                    {event.category ? ` · ${te(`categories.${event.category}`)}` : ""}
                  </p>
                  {event.tickets_sold > 0 ? (
                    <p className="text-xs text-text-2">
                      {t("events.list.ticketsSold", { count: event.tickets_sold })}
                    </p>
                  ) : null}
                </div>
                <Badge
                  variant={statusBadgeVariant(event.status)}
                  label={t(`events.status.${event.status}`)}
                />
              </div>
              <Link
                href={`/${locale}/events/${event.id}/edit`}
                className="mt-3 inline-flex min-h-11 w-full items-center justify-center rounded-md border border-border px-4 text-sm font-medium"
              >
                {t("events.list.editCta")}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
