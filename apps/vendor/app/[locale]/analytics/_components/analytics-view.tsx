"use client";

import { useSession } from "@vergeo/auth/use-session";
import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Spinner } from "../../../../../../packages/ui/src/spinner";
import { VendorEmptyState, VendorErrorState } from "../../_components/async-state";
import { vendorErrorMessageKey } from "../../_lib/vendor-errors";
import { createAnalyticsClient, type AnalyticsWindow } from "../_lib/analytics-client";

import { Sparkline } from "./sparkline";

import type { VendorAnalytics } from "../_lib/analytics-client";

const WINDOWS: AnalyticsWindow[] = [7, 30];

type StatCardProps = {
  label: string;
  value: string;
  sparklineLabel: string;
  series: number[];
};

function StatCard({ label, value, sparklineLabel, series }: StatCardProps) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4">
      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span className="font-mono text-lg font-semibold">{value}</span>
      <Sparkline label={sparklineLabel} values={series} />
    </div>
  );
}

export function AnalyticsView() {
  const t = useTranslations("vendor");
  const tCommon = useTranslations("common");
  const { session, loading: sessionLoading } = useSession();
  const [window, setWindow] = useState<AnalyticsWindow>(7);
  const [data, setData] = useState<VendorAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const analyticsClient = useMemo(() => createAnalyticsClient(getToken), [getToken]);

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
    setErrorKey(null);
    void analyticsClient
      .get(window)
      .then((result) => {
        if (!cancelled) {
          setData(result);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setData(null);
          setErrorKey(vendorErrorMessageKey(caught, "analytics"));
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
  }, [analyticsClient, reloadKey, session, sessionLoading, window]);

  const totals = useMemo(() => {
    if (!data) {
      return { sales: 0, orders: 0, views: 0 };
    }
    const sum = (values: number[]) => values.reduce((acc, value) => acc + value, 0);
    return {
      sales: sum(data.sales_ngwee_by_day),
      orders: sum(data.orders_by_day),
      views: sum(data.views_by_day),
    };
  }, [data]);

  const isEmpty = totals.sales === 0 && totals.orders === 0 && totals.views === 0;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <p className="text-sm text-muted-foreground">{t("analytics.eyebrow")}</p>
        <h1 className="font-display text-2xl font-semibold">{t("analytics.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("analytics.intro")}</p>
      </header>

      <div
        aria-label={t("analytics.window.label")}
        className="inline-flex w-fit rounded-lg border border-border p-1"
        role="group"
      >
        {WINDOWS.map((value) => {
          const active = value === window;
          return (
            <button
              aria-pressed={active}
              className={`min-h-11 rounded-md px-4 text-sm font-medium ${
                active ? "bg-primary text-primary-foreground" : "text-muted-foreground"
              }`}
              key={value}
              onClick={() => setWindow(value)}
              type="button"
            >
              {value === 7 ? t("analytics.window.7d") : t("analytics.window.30d")}
            </button>
          );
        })}
      </div>

      {!session && !sessionLoading ? (
        <VendorErrorState
          title={t("analytics.errors.authRequired")}
          retryLabel={tCommon("common.retry")}
        />
      ) : null}

      {errorKey ? (
        <VendorErrorState
          title={t(errorKey as "analytics.errors.loadFailed")}
          body={t("analytics.errors.retryHint")}
          retryLabel={tCommon("common.retry")}
          onRetry={() => setReloadKey((value) => value + 1)}
        />
      ) : null}

      {loading ? (
        <div className="flex min-h-[40vh] items-center justify-center">
          <Spinner label={t("analytics.loading")} />
        </div>
      ) : null}

      {!loading && !errorKey && data && isEmpty ? (
        <VendorEmptyState title={t("analytics.empty.title")} body={t("analytics.empty.body")} />
      ) : null}

      {!loading && !errorKey && data && !isEmpty ? (
        <>
          <section className="grid gap-3">
            <StatCard
              label={t("analytics.cards.sales")}
              series={data.sales_ngwee_by_day}
              sparklineLabel={t("analytics.sparkline.sales")}
              value={formatK(totals.sales)}
            />
            <StatCard
              label={t("analytics.cards.orders")}
              series={data.orders_by_day}
              sparklineLabel={t("analytics.sparkline.orders")}
              value={String(totals.orders)}
            />
            <StatCard
              label={t("analytics.cards.views")}
              series={data.views_by_day}
              sparklineLabel={t("analytics.sparkline.views")}
              value={String(totals.views)}
            />
          </section>

          <section className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              {t("analytics.conversion.heading")}
            </h2>
            {data.conversion_hint.views_total > 0 ? (
              <>
                <p className="font-mono text-lg font-semibold">
                  {t("analytics.conversion.pct", {
                    pct: data.conversion_hint.conversion_pct,
                  })}
                </p>
                <p className="text-sm text-muted-foreground">
                  {t("analytics.conversion.summary", {
                    orders: data.conversion_hint.orders_total,
                    views: data.conversion_hint.views_total,
                  })}
                </p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">{t("analytics.conversion.empty")}</p>
            )}
          </section>

          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              {t("analytics.top.heading")}
            </h2>
            {data.top_listings.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("analytics.top.empty")}</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {data.top_listings.map((listing) => (
                  <li
                    className="flex items-center justify-between gap-3 rounded-lg border border-border p-3"
                    key={listing.listing_id}
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {listing.title || t("analytics.top.untitled")}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {t("analytics.top.units", { count: listing.units })}
                      </p>
                    </div>
                    <span className="font-mono text-sm font-semibold">
                      {formatK(listing.revenue_ngwee)}
                    </span>
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
