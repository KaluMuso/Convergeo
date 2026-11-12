"use client";

import { ApiError } from "@vergeo/config";
import { formatK, formatNumber } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { classifyAdminRequestError } from "../../_components/admin-request";
import { dashboardApi } from "../../_components/api";
import { TileShell } from "../../_components/TileShell";

import {
  ANALYTICS_TABS,
  RANGE_DAYS,
  analyticsPath,
  bpsToFraction,
  rangeEndingYesterday,
  relativeChange,
  splitSeconds,
  type AnalyticsTab,
  type InsightsData,
  type OverviewData,
  type ProductsFunnelData,
  type RangeDays,
  type SearchDemandData,
} from "./analytics-data";
import { BarList } from "./bar-list";

type LoadState<T> =
  | { kind: "loading" }
  | { kind: "disabled" }
  | { kind: "permission" }
  | { kind: "error" }
  | { kind: "ready"; data: T };

type ViewProps = { locale: string; tab: AnalyticsTab };

/**
 * Admin analytics shell (1B-05): tabs, range picker and the flag gate. Reads aggregates
 * only from `/admin/analytics/*`; when `analytics_v2_rollups` is off the API answers 404
 * `analytics_disabled` and this renders a "not enabled" panel instead of any data.
 */
export function AnalyticsView({ locale, tab }: ViewProps) {
  const t = useTranslations("admin.analytics");
  const [days, setDays] = useState<RangeDays>(7);
  const [state, setState] = useState<LoadState<unknown>>({ kind: "loading" });
  const api = ANALYTICS_TABS.find((entry) => entry.tab === tab)?.api ?? "overview";

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const data = await dashboardApi.request<unknown>(
        analyticsPath(api, rangeEndingYesterday(days)),
      );
      setState({ kind: "ready", data });
    } catch (err) {
      if (err instanceof ApiError && err.code === "analytics_disabled") {
        setState({ kind: "disabled" });
        return;
      }
      setState({
        kind: classifyAdminRequestError(err).kind === "permission" ? "permission" : "error",
      });
    }
  }, [api, days]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="font-serif text-xl text-text">{t("title")}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </header>

      <nav aria-label={t("tabs.label")} className="flex flex-wrap gap-2">
        {ANALYTICS_TABS.map((entry) => {
          const active = entry.tab === tab;
          return (
            <Link
              key={entry.tab}
              href={`/${locale}/${entry.href}`}
              aria-current={active ? "page" : undefined}
              className={[
                "inline-flex min-h-11 items-center rounded-md border px-3 text-sm font-medium",
                active
                  ? "border-primary bg-surface text-primary"
                  : "border-border bg-surface text-text hover:border-primary",
              ].join(" ")}
            >
              {t(`tabs.${entry.tab}`)}
            </Link>
          );
        })}
      </nav>

      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="sr-only">{t("range.label")}</legend>
        {RANGE_DAYS.map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={option === days}
            onClick={() => setDays(option)}
            className={[
              "inline-flex min-h-11 items-center rounded-md border px-3 text-sm",
              option === days ? "border-primary text-primary" : "border-border text-text",
            ].join(" ")}
          >
            {t("range.days", { days: option })}
          </button>
        ))}
      </fieldset>

      {state.kind === "loading" ? <p className="text-sm text-muted">{t("loading")}</p> : null}
      {state.kind === "disabled" ? (
        <div
          className="space-y-1 rounded-md border border-border bg-surface p-4"
          data-testid="analytics-disabled"
        >
          <p className="text-sm font-medium text-text">{t("disabled.title")}</p>
          <p className="text-xs text-muted">{t("disabled.body")}</p>
        </div>
      ) : null}
      {state.kind === "permission" ? (
        <p className="text-sm text-warning">{t("permissionDenied")}</p>
      ) : null}
      {state.kind === "error" ? (
        <div className="space-y-2">
          <p className="text-sm text-danger">{t("error")}</p>
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
            onClick={() => void load()}
          >
            {t("retry")}
          </button>
        </div>
      ) : null}
      {state.kind === "ready" ? <TabBody tab={tab} data={state.data} locale={locale} /> : null}
    </div>
  );
}

export function TabBody({
  tab,
  data,
  locale,
}: {
  tab: AnalyticsTab;
  data: unknown;
  locale: string;
}) {
  switch (tab) {
    case "overview":
      return <OverviewTab data={data as OverviewData} locale={locale} />;
    case "search":
      return <SearchTab data={data as SearchDemandData} locale={locale} />;
    case "products":
      return <ProductsTab data={data as ProductsFunnelData} locale={locale} />;
    case "insights":
      return <InsightsTab data={data as InsightsData} />;
  }
}

function DataThrough({ day }: { day: string | null }) {
  const t = useTranslations("admin.analytics");
  return <p className="text-xs text-muted">{day ? t("dataThrough", { day }) : t("dataPending")}</p>;
}

function Kpi({ label, value, hint }: { label: string; value: string; hint?: ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-bg p-3">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 font-mono text-xl font-semibold text-text">{value}</p>
      {hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

function usePercent(locale: string, minSample: number) {
  const t = useTranslations("admin.analytics");
  return (bps: number | null): string =>
    bps === null
      ? t("insufficient", { n: minSample })
      : formatNumber(bpsToFraction(bps), locale, { style: "percent", maximumFractionDigits: 1 });
}

function useDelta(locale: string) {
  const t = useTranslations("admin.analytics");
  return (current: number, previous: number): string => {
    const change = relativeChange(current, previous);
    if (change === null) {
      return t("delta.none");
    }
    return t("delta.value", {
      change: formatNumber(change, locale, {
        style: "percent",
        maximumFractionDigits: 0,
        signDisplay: "exceptZero",
      }),
    });
  };
}

function OverviewTab({ data, locale }: { data: OverviewData; locale: string }) {
  const t = useTranslations("admin.analytics");
  const percent = usePercent(locale, data.min_sample_n);
  const delta = useDelta(locale);
  const { behaviour: b, commercial: c, previous_commercial: pc } = data;
  const span = b.avg_active_span_seconds === null ? null : splitSeconds(b.avg_active_span_seconds);
  const num = (value: number) => formatNumber(value, locale);

  return (
    <div className="space-y-4">
      <DataThrough day={data.data_through} />
      {!c.payments_reconciled ? (
        <p className="rounded-md border border-danger/40 p-3 text-sm text-danger" role="alert">
          {t("overview.reconciliation.mismatch", { days: c.payment_mismatch_days.join(", ") })}
        </p>
      ) : null}

      <TileShell title={t("overview.commercialTitle")} subtitle={t("overview.commercialHint")}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Kpi
            label={t("overview.kpi.gmvPaid")}
            value={formatK(c.gmv_paid_ngwee, { locale })}
            hint={delta(c.gmv_paid_ngwee, pc.gmv_paid_ngwee)}
          />
          <Kpi
            label={t("overview.kpi.ordersPaid")}
            value={num(c.orders_paid)}
            hint={delta(c.orders_paid, pc.orders_paid)}
          />
          <Kpi
            label={t("overview.kpi.aov")}
            value={c.aov_ngwee === null ? t("notAvailable") : formatK(c.aov_ngwee, { locale })}
          />
          <Kpi
            label={t("overview.kpi.checkoutsStarted")}
            value={num(c.checkouts_started)}
            hint={t("overview.kpi.ordersPlacedHint", { placed: c.orders_placed })}
          />
        </div>
      </TileShell>

      <TileShell title={t("overview.behaviourTitle")} subtitle={t("session.rule")}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Kpi label={t("overview.kpi.sessions")} value={num(b.sessions)} />
          <Kpi label={t("overview.kpi.visitorDays")} value={num(b.visitor_days)} />
          <Kpi label={t("overview.kpi.bounceRate")} value={percent(b.bounce_rate_bps)} />
          <Kpi
            label={t("session.activeSpan")}
            value={
              span === null
                ? t("insufficient", { n: data.min_sample_n })
                : t("session.duration", span)
            }
            hint={t("session.estimatedEnd")}
          />
          <Kpi label={t("overview.kpi.searches")} value={num(b.searches)} />
          <Kpi label={t("overview.kpi.zeroResultShare")} value={percent(b.zero_result_share_bps)} />
        </div>
      </TileShell>

      <TileShell title={t("overview.dailyTitle")}>
        <BarList
          caption={t("overview.dailyTitle")}
          emptyLabel={t("empty")}
          labelHeader={t("columns.day")}
          valueHeader={t("overview.kpi.gmvPaid")}
          items={data.daily.map((day) => ({
            key: day.day,
            label: day.day,
            value: day.gmv_paid_ngwee,
            display: formatK(day.gmv_paid_ngwee, { locale }),
          }))}
        />
      </TileShell>
    </div>
  );
}

function SearchTab({ data, locale }: { data: SearchDemandData; locale: string }) {
  const t = useTranslations("admin.analytics");
  const percent = usePercent(locale, data.min_sample_n);
  const num = (value: number) => formatNumber(value, locale);
  return (
    <div className="space-y-4">
      <DataThrough day={data.data_through} />
      <p className="text-xs text-muted">{t("search.kNotice", { k: data.k })}</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <Kpi label={t("overview.kpi.searches")} value={num(data.totals.searches)} />
        <Kpi label={t("search.zeroResults")} value={num(data.totals.zero_results)} />
        <Kpi
          label={t("overview.kpi.zeroResultShare")}
          value={percent(data.totals.zero_result_share_bps)}
        />
      </div>
      <TileShell title={t("search.zeroTitle")} subtitle={t("search.zeroHint")}>
        <BarList
          caption={t("search.zeroTitle")}
          emptyLabel={t("empty")}
          labelHeader={t("columns.term")}
          valueHeader={t("search.zeroResults")}
          items={data.zero_result_terms.map((term) => ({
            key: term.normalized_term,
            label: term.normalized_term,
            value: term.zero_results,
            display: num(term.zero_results),
          }))}
        />
      </TileShell>
      <TileShell title={t("search.topTitle")}>
        <BarList
          caption={t("search.topTitle")}
          emptyLabel={t("empty")}
          labelHeader={t("columns.term")}
          valueHeader={t("overview.kpi.searches")}
          items={data.top_terms.map((term) => ({
            key: term.normalized_term,
            label: term.normalized_term,
            value: term.searches,
            display: num(term.searches),
          }))}
        />
        <p className="mt-3 text-xs text-muted">
          {t("search.other", { terms: data.other.terms, searches: data.other.searches })}
        </p>
      </TileShell>
    </div>
  );
}

function ProductsTab({ data, locale }: { data: ProductsFunnelData; locale: string }) {
  const t = useTranslations("admin.analytics");
  const percent = usePercent(locale, data.min_sample_n);
  const num = (value: number) => formatNumber(value, locale);
  return (
    <div className="space-y-4">
      <DataThrough day={data.data_through} />
      <TileShell title={t("products.funnelTitle")} subtitle={t("products.funnelHint")}>
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {data.funnel.map((step) => (
            <li key={step.step}>
              <Kpi
                label={t(`products.steps.${step.step}`)}
                value={num(step.value)}
                hint={t("products.shareOfSessions", {
                  share: percent(step.share_of_sessions_bps),
                })}
              />
            </li>
          ))}
        </ol>
      </TileShell>
      <TileShell title={t("products.topTitle")}>
        <BarList
          caption={t("products.topTitle")}
          emptyLabel={t("empty")}
          labelHeader={t("columns.product")}
          valueHeader={t("products.views")}
          items={data.top_products.map((product) => ({
            key: product.product_id,
            label: product.name ?? t("products.unnamed"),
            value: product.views,
            display: num(product.views),
          }))}
        />
      </TileShell>
      <div className="grid gap-4 lg:grid-cols-2">
        <TileShell title={t("products.pageViewsTitle")}>
          <BarList
            caption={t("products.pageViewsTitle")}
            emptyLabel={t("empty")}
            labelHeader={t("columns.page")}
            valueHeader={t("products.views")}
            items={data.page_views.map((page) => ({
              key: page.page_key,
              label: page.page_key,
              value: page.views,
              display: num(page.views),
            }))}
          />
        </TileShell>
        <TileShell title={t("products.entryTitle")}>
          <BarList
            caption={t("products.entryTitle")}
            emptyLabel={t("empty")}
            labelHeader={t("columns.page")}
            valueHeader={t("overview.kpi.sessions")}
            items={data.entry_pages.map((page) => ({
              key: page.page_key,
              label: page.page_key,
              value: page.sessions,
              display: num(page.sessions),
            }))}
          />
        </TileShell>
      </div>
    </div>
  );
}

function InsightsTab({ data }: { data: InsightsData }) {
  const t = useTranslations("admin.analytics");
  return (
    <div className="space-y-4">
      <DataThrough day={data.data_through} />
      <p className="text-sm text-muted">{t("insights.placeholder")}</p>
      {data.items.length === 0 ? (
        <p className="text-sm text-success" data-testid="insights-empty">
          {t("insights.none")}
        </p>
      ) : (
        <ul className="space-y-2">
          {data.items.map((item) => (
            <li
              key={`${item.kind}-${item.day ?? "none"}`}
              className={`rounded-md border p-3 text-sm ${
                item.severity === "high" ? "border-danger/40 text-danger" : "border-warning/40"
              }`}
            >
              {t(`insights.kinds.${item.kind}`, { day: item.day ?? t("notAvailable") })}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
