"use client";

import { useSession } from "@vergeo/auth/use-session";
import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Spinner } from "../../../../listings/new/_lib/ui";
import { createDashboardClient, type OrganiserEventStats } from "../_lib/dashboard-client";

type EventDashboardProps = {
  locale: string;
  eventId: string;
};

const CHECK_IN_POLL_MS = 15_000;

export function EventDashboard({ locale, eventId }: EventDashboardProps) {
  const t = useTranslations("vendor");
  const { session, loading: sessionLoading } = useSession();
  const [stats, setStats] = useState<OrganiserEventStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const dashboardClient = useMemo(() => createDashboardClient(getToken), [getToken]);

  const loadStats = useCallback(
    async ({ silent }: { silent: boolean }) => {
      if (!silent) {
        setLoading(true);
      }
      setError(null);
      try {
        const next = await dashboardClient.getEventStats(eventId);
        setStats(next);
      } catch {
        setError(t("eventDashboard.errors.loadFailed"));
      } finally {
        if (!silent) {
          setLoading(false);
        }
      }
    },
    [dashboardClient, eventId, t],
  );

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }
    void loadStats({ silent: false });
  }, [loadStats, session, sessionLoading]);

  // Live-ish poll for check-in progress while the dashboard is open.
  useEffect(() => {
    if (sessionLoading || !session) {
      return;
    }
    const interval = window.setInterval(() => {
      void loadStats({ silent: true });
    }, CHECK_IN_POLL_MS);
    return () => window.clearInterval(interval);
  }, [loadStats, session, sessionLoading]);

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("eventDashboard.loading")} />
        <span className="sr-only">{t("eventDashboard.loading")}</span>
      </div>
    );
  }

  if (!session) {
    return (
      <p className="text-sm text-muted-foreground">{t("eventDashboard.errors.unauthorized")}</p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="font-display text-xl font-semibold">{t("eventDashboard.heading")}</h1>
        <p className="text-sm text-muted-foreground">{t("eventDashboard.subheading")}</p>
      </div>

      <Link
        href={`/${locale}/events/${eventId}/edit`}
        className="text-sm font-medium text-primary underline-offset-2 hover:underline"
      >
        {t("eventDashboard.backToEvent")}
      </Link>

      {error ? (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}

      {stats?.mass_refund_flagged ? (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
          {t("eventDashboard.massRefundFlagged")}
        </p>
      ) : null}

      {stats ? (
        <>
          <section className="rounded-lg border border-border bg-card p-3 shadow-sm">
            <h2 className="text-sm font-semibold">{t("eventDashboard.sections.revenue")}</h2>
            <p className="text-2xl font-semibold">{formatK(stats.revenue_ngwee)}</p>
          </section>

          <section className="rounded-lg border border-border bg-card p-3 shadow-sm">
            <h2 className="text-sm font-semibold">{t("eventDashboard.sections.checkIn")}</h2>
            <p className="text-sm text-muted-foreground">
              {t("eventDashboard.checkInProgress", {
                checkedIn: stats.check_in.checked_in,
                issued: stats.check_in.issued,
              })}
            </p>
          </section>

          <section className="rounded-lg border border-border bg-card p-3 shadow-sm">
            <h2 className="text-sm font-semibold">{t("eventDashboard.sections.escrow")}</h2>
            <dl className="mt-1 flex flex-col gap-1 text-sm">
              <div className="flex items-center justify-between">
                <dt className="text-muted-foreground">{t("eventDashboard.labels.pending")}</dt>
                <dd className="font-medium">{formatK(stats.escrow.pending_ngwee)}</dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-muted-foreground">{t("eventDashboard.labels.released")}</dt>
                <dd className="font-medium">{formatK(stats.escrow.released_ngwee)}</dd>
              </div>
            </dl>
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="text-sm font-semibold">{t("eventDashboard.sections.salesByType")}</h2>
            {stats.sales_by_type.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("eventDashboard.empty")}</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {stats.sales_by_type.map((row) => (
                  <li
                    key={row.ticket_type_id}
                    className="rounded-lg border border-border bg-card p-3 shadow-sm"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-medium">{row.name}</p>
                      <p className="font-medium">{formatK(row.revenue_ngwee)}</p>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {t("eventDashboard.labels.soldCheckedIn", {
                        sold: row.sold,
                        checkedIn: row.checked_in,
                      })}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
