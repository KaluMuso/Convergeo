"use client";

import { useSession } from "@vergeo/auth/use-session";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button, Spinner } from "../../../../listings/new/_lib/ui";
import { groupByInstance } from "../_lib/group-roster";
import { createRosterClient, type OrganiserEventRoster } from "../_lib/roster-client";

type RosterViewProps = {
  locale: string;
  eventId: string;
};

function formatInstanceDate(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "Africa/Lusaka",
  }).format(new Date(iso));
}

export function RosterView({ locale, eventId }: RosterViewProps) {
  const t = useTranslations("vendor");
  const { session, loading: sessionLoading } = useSession();
  const [roster, setRoster] = useState<OrganiserEventRoster | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const rosterClient = useMemo(() => createRosterClient(getToken), [getToken]);

  const loadRoster = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRoster(await rosterClient.getEventRoster(eventId));
    } catch {
      setError(t("eventRoster.errors.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [eventId, rosterClient, t]);

  const handleDownload = useCallback(async () => {
    setDownloading(true);
    setError(null);
    try {
      const blob = await rosterClient.downloadRosterCsv(eventId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `roster-${eventId}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(t("eventRoster.errors.downloadFailed"));
    } finally {
      setDownloading(false);
    }
  }, [eventId, rosterClient, t]);

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }
    void loadRoster();
  }, [loadRoster, session, sessionLoading]);

  const groups = useMemo(() => (roster ? groupByInstance(roster.attendees) : []), [roster]);

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("eventRoster.loading")} />
        <span className="sr-only">{t("eventRoster.loading")}</span>
      </div>
    );
  }

  if (!session) {
    return <p className="text-sm text-muted-foreground">{t("eventRoster.errors.unauthorized")}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="font-display text-xl font-semibold">{t("eventRoster.heading")}</h1>
        <p className="text-sm text-muted-foreground">{t("eventRoster.subheading")}</p>
      </div>

      <Link
        href={`/${locale}/events/${eventId}/dashboard`}
        className="text-sm font-medium text-primary underline-offset-2 hover:underline"
      >
        {t("eventRoster.backToDashboard")}
      </Link>

      {error ? (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}

      {roster ? (
        <>
          <section className="flex flex-col gap-2 rounded-lg border border-border bg-card p-3 shadow-sm">
            <p className="text-sm text-muted-foreground">
              {t("eventRoster.summary", {
                checkedIn: roster.checked_in,
                total: roster.total,
              })}
            </p>
            {roster.total > 0 ? (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => void handleDownload()}
                disabled={downloading}
                loading={downloading}
                loadingLabel={t("eventRoster.downloading")}
              >
                {t("eventRoster.downloadCsv")}
              </Button>
            ) : null}
          </section>

          {roster.truncated ? (
            <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
              {t("eventRoster.truncated", { count: roster.attendees.length })}
            </p>
          ) : null}

          {roster.total === 0 ? (
            <p className="text-sm text-muted-foreground">{t("eventRoster.empty")}</p>
          ) : (
            <div className="flex flex-col gap-4">
              {groups.map((group) => (
                <section key={group.instanceId} className="flex flex-col gap-2">
                  <div className="flex items-baseline justify-between gap-2">
                    <h2 className="text-sm font-semibold">
                      {formatInstanceDate(group.startsAt, locale)}
                    </h2>
                    <span className="text-xs text-muted-foreground">
                      {t("eventRoster.dateCount", { count: group.attendees.length })}
                    </span>
                  </div>
                  <ul className="flex flex-col gap-1.5">
                    {group.attendees.map((attendee) => (
                      <li
                        key={attendee.ticket_id}
                        className="flex items-center justify-between gap-2 rounded-lg border border-border bg-card p-3 shadow-sm"
                      >
                        <div className="min-w-0">
                          <p className="truncate font-medium">
                            {attendee.holder_name ?? (
                              <span className="italic text-muted-foreground">
                                {t("eventRoster.noName")}
                              </span>
                            )}
                          </p>
                          <p className="truncate text-xs text-muted-foreground">
                            {attendee.ticket_type_name}
                          </p>
                        </div>
                        <span
                          className={
                            attendee.status === "checked_in"
                              ? "shrink-0 text-xs font-medium text-primary"
                              : "shrink-0 text-xs text-muted-foreground"
                          }
                        >
                          {attendee.status === "checked_in"
                            ? t("eventRoster.status.checkedIn")
                            : t("eventRoster.status.issued")}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
