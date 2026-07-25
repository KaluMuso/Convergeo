"use client";

import { useSession } from "@vergeo/auth/use-session";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { EventForm } from "../../../_components/event-form";
import { createEventsClient, type EventDetail } from "../../../_lib/events-client";
import { Spinner } from "../../../_lib/ui";

type EventEditViewProps = {
  locale: string;
  eventId: string;
};

export function EventEditView({ locale, eventId }: EventEditViewProps) {
  const t = useTranslations("vendor");
  const { session, loading: sessionLoading } = useSession();
  const [event, setEvent] = useState<EventDetail | null>(null);
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
      .getEvent(eventId)
      .then((response) => {
        if (!cancelled) {
          setEvent(response.event);
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
  }, [eventId, eventsClient, session, sessionLoading, t]);

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("events.list.loading")} />
      </div>
    );
  }

  if (error) {
    return <p className="text-sm text-danger">{error}</p>;
  }

  if (!event) {
    return null;
  }

  return <EventForm locale={locale} mode="edit" eventId={eventId} initialEvent={event} />;
}
