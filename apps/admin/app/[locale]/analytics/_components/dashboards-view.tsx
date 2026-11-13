"use client";

import { formatK, formatNumber } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { AnalyticsExportError, downloadAnalyticsCsv } from "../../../../lib/analytics-export";
import { useAdminPermissions } from "../../../../lib/roles-api";
import { classifyAdminRequestError } from "../../_components/admin-request";
import { dashboardApi } from "../../_components/api";
import { TileShell } from "../../_components/TileShell";

import { bpsToFraction, relativeChange } from "./analytics-data";
import { AnalyticsTabs } from "./analytics-tabs";
import { BarList } from "./bar-list";
import {
  ALL_ANALYTICS_TABS,
  GROWTH_KEYS,
  KYC_STATUSES,
  PERIODS,
  VENDOR_STATUSES,
  allZero,
  exportFilename,
  grantsAllow,
  lusakaToday,
  periodQuery,
  ratingText,
  type DashboardTab,
  type GrowthData,
  type PeriodSelection,
  type RevenueData,
  type ServicesEventsData,
  type UsersData,
  type VendorsData,
} from "./dashboards-data";

type LoadState<T> =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "permission" }
  | { kind: "error" }
  | { kind: "ready"; data: T };

type ExportState = "idle" | "working" | "done" | "permission" | "error";

/**
 * Founder dashboards (users, growth, revenue, vendors, services & events): period picker
 * (today / 7 days / 30 days / custom, Africa/Lusaka days), loading, empty, error and
 * permission states, and an audited CSV export of the report on screen.
 */
export function DashboardsView({ locale, tab }: { locale: string; tab: DashboardTab }) {
  const t = useTranslations("admin.analytics");
  const grants = useAdminPermissions();
  const entry = ALL_ANALYTICS_TABS.find((item) => item.tab === tab);
  const api = entry?.api ?? "users";
  const allowed = entry ? grantsAllow(grants, entry.needs) : false;
  const [selection, setSelection] = useState<PeriodSelection>({ period: "7d" });
  const [draft, setDraft] = useState<{ from: string; to: string }>({ from: "", to: "" });
  const [state, setState] = useState<LoadState<unknown>>({ kind: "idle" });
  const [exportState, setExportState] = useState<ExportState>("idle");
  const query = periodQuery(selection);

  const load = useCallback(async () => {
    if (!allowed) {
      setState({ kind: "permission" });
      return;
    }
    if (query === null) {
      setState({ kind: "idle" });
      return;
    }
    setState({ kind: "loading" });
    try {
      const data = await dashboardApi.request<unknown>(`/admin/analytics/${api}?${query}`);
      setState({ kind: "ready", data });
    } catch (err) {
      setState({
        kind: classifyAdminRequestError(err).kind === "permission" ? "permission" : "error",
      });
    }
  }, [allowed, api, query]);

  useEffect(() => {
    void load();
  }, [load]);

  const runExport = async () => {
    if (query === null || state.kind !== "ready") {
      return;
    }
    setExportState("working");
    const range = (state.data as { range: { from: string; to: string } }).range;
    try {
      await downloadAnalyticsCsv(api, query, exportFilename(api, range));
      setExportState("done");
    } catch (err) {
      setExportState(
        err instanceof AnalyticsExportError && err.kind === "permission" ? "permission" : "error",
      );
    }
  };

  const today = lusakaToday();

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="font-serif text-xl text-text">{t("title")}</h1>
        <p className="text-sm text-muted">{t("dash.subtitle")}</p>
      </header>

      <AnalyticsTabs locale={locale} active={tab} />

      <div className="flex flex-wrap items-end gap-2">
        <fieldset className="flex flex-wrap items-center gap-2">
          <legend className="sr-only">{t("range.label")}</legend>
          {PERIODS.map((period) => (
            <button
              key={period}
              type="button"
              aria-pressed={period === selection.period}
              onClick={() =>
                setSelection(
                  period === "custom" ? { period, from: draft.from, to: draft.to } : { period },
                )
              }
              className={[
                "inline-flex min-h-11 items-center rounded-md border px-3 text-sm",
                period === selection.period
                  ? "border-primary text-primary"
                  : "border-border text-text",
              ].join(" ")}
            >
              {t(`dash.period.${period}`)}
            </button>
          ))}
        </fieldset>
        {selection.period === "custom" ? (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              setSelection({ period: "custom", from: draft.from, to: draft.to });
            }}
          >
            <label className="flex flex-col text-xs text-muted">
              {t("dash.period.from")}
              <input
                type="date"
                required
                max={today}
                value={draft.from}
                onChange={(event) => setDraft((d) => ({ ...d, from: event.target.value }))}
                className="min-h-11 rounded-md border border-border bg-surface px-2 text-sm text-text"
              />
            </label>
            <label className="flex flex-col text-xs text-muted">
              {t("dash.period.to")}
              <input
                type="date"
                required
                max={today}
                value={draft.to}
                onChange={(event) => setDraft((d) => ({ ...d, to: event.target.value }))}
                className="min-h-11 rounded-md border border-border bg-surface px-2 text-sm text-text"
              />
            </label>
            <button
              type="submit"
              className="inline-flex min-h-11 items-center rounded-md border border-primary px-3 text-sm text-primary"
            >
              {t("dash.period.apply")}
            </button>
          </form>
        ) : null}
        <button
          type="button"
          onClick={() => void runExport()}
          disabled={state.kind !== "ready" || exportState === "working"}
          className="ml-auto inline-flex min-h-11 items-center rounded-md border border-border px-3 text-sm text-text disabled:opacity-60"
        >
          {exportState === "working" ? t("dash.export.working") : t("dash.export.button")}
        </button>
      </div>
      <p className="text-xs text-muted">{t("dash.lusakaNote")}</p>
      {exportState === "done" ? (
        <p className="text-xs text-muted" role="status">
          {t("dash.export.done")}
        </p>
      ) : null}
      {exportState === "permission" ? (
        <p className="text-sm text-warning" role="alert">
          {t("dash.export.permission")}
        </p>
      ) : null}
      {exportState === "error" ? (
        <p className="text-sm text-danger" role="alert">
          {t("dash.export.error")}
        </p>
      ) : null}

      {state.kind === "idle" && selection.period === "custom" ? (
        <p className="text-sm text-muted">{t("dash.period.customHint")}</p>
      ) : null}
      {state.kind === "loading" ? (
        <p className="text-sm text-muted" role="status">
          {t("loading")}
        </p>
      ) : null}
      {state.kind === "permission" ? (
        <p className="text-sm text-warning" role="alert" data-testid="dash-permission">
          {tab === "revenue" ? t("dash.permissionFinance") : t("permissionDenied")}
        </p>
      ) : null}
      {state.kind === "error" ? (
        <div className="space-y-2">
          <p className="text-sm text-danger" role="alert">
            {t("error")}
          </p>
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
            onClick={() => void load()}
          >
            {t("retry")}
          </button>
        </div>
      ) : null}
      {state.kind === "ready" ? (
        <DashboardBody tab={tab} data={state.data} locale={locale} />
      ) : null}
    </div>
  );
}

export function DashboardBody({
  tab,
  data,
  locale,
}: {
  tab: DashboardTab;
  data: unknown;
  locale: string;
}) {
  switch (tab) {
    case "users":
      return <UsersTab data={data as UsersData} locale={locale} />;
    case "growth":
      return <GrowthTab data={data as GrowthData} locale={locale} />;
    case "revenue":
      return <RevenueTab data={data as RevenueData} locale={locale} />;
    case "vendors":
      return <VendorsTab data={data as VendorsData} locale={locale} />;
    case "servicesEvents":
      return <ServicesEventsTab data={data as ServicesEventsData} locale={locale} />;
  }
}

// ---------------------------------------------------------------------------
// Shared pieces
// ---------------------------------------------------------------------------

function Kpi({ label, value, hint }: { label: string; value: string; hint?: ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-bg p-3">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 font-mono text-xl font-semibold text-text">{value}</p>
      {hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

function KpiGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{children}</div>;
}

function useFormat(locale: string) {
  const t = useTranslations("admin.analytics");
  const num = (value: number) => formatNumber(value, locale);
  const money = (ngwee: number) => formatK(ngwee, { locale });
  const percent = (bps: number | null) =>
    bps === null
      ? t("notAvailable")
      : formatNumber(bpsToFraction(bps), locale, { style: "percent", maximumFractionDigits: 1 });
  const delta = (current: number, previous: number) => {
    const change = relativeChange(current, previous);
    return change === null
      ? t("delta.none")
      : t("delta.value", {
          change: formatNumber(change, locale, {
            style: "percent",
            maximumFractionDigits: 0,
            signDisplay: "exceptZero",
          }),
        });
  };
  return { num, money, percent, delta };
}

type Column<Row> = { key: string; label: string; render: (row: Row) => string };

function DailyTable<Row extends { day: string }>({
  caption,
  rows,
  columns,
}: {
  caption: string;
  rows: Row[];
  columns: Array<Column<Row>>;
}) {
  const t = useTranslations("admin.analytics");
  if (rows.length === 0 || allZero(rows)) {
    return <p className="text-sm text-muted">{t("dash.noActivity")}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[20rem] text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="text-left text-xs text-muted">
            <th scope="col" className="py-1 pr-3 font-medium">
              {t("columns.day")}
            </th>
            {columns.map((column) => (
              <th key={column.key} scope="col" className="py-1 pr-3 text-right font-medium">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.day} className="border-t border-border">
              <th scope="row" className="py-1 pr-3 text-left font-normal text-text">
                {row.day}
              </th>
              {columns.map((column) => (
                <td key={column.key} className="py-1 pr-3 text-right font-mono text-xs">
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

function UsersTab({ data, locale }: { data: UsersData; locale: string }) {
  const t = useTranslations("admin.analytics");
  const { num, percent, delta } = useFormat(locale);
  const activity = data.activity;
  return (
    <div className="space-y-4">
      <TileShell title={t("dash.users.title")} subtitle={t("dash.users.hint")}>
        <KpiGrid>
          <Kpi label={t("dash.users.customers")} value={num(data.totals.customers)} />
          <Kpi
            label={t("dash.users.vendors")}
            value={num(data.totals.vendors)}
            hint={t("dash.users.activeVendors", { n: data.totals.active_vendors })}
          />
          <Kpi
            label={t("dash.users.newCustomers")}
            value={num(data.new.customers)}
            hint={delta(data.new.customers, data.previous_new.customers)}
          />
          <Kpi
            label={t("dash.users.newVendors")}
            value={num(data.new.vendors)}
            hint={delta(data.new.vendors, data.previous_new.vendors)}
          />
        </KpiGrid>
      </TileShell>

      <TileShell title={t("dash.users.registrations")}>
        <DailyTable
          caption={t("dash.users.registrations")}
          rows={data.daily}
          columns={[
            { key: "c", label: t("dash.users.customers"), render: (r) => num(r.customers) },
            { key: "v", label: t("dash.users.vendors"), render: (r) => num(r.vendors) },
          ]}
        />
      </TileShell>

      <TileShell title={t("dash.users.activityTitle")} subtitle={t("dash.users.activityHint")}>
        {activity.enabled ? (
          <div className="space-y-3">
            <KpiGrid>
              <Kpi
                label={t("dash.users.dau")}
                value={num(activity.dau)}
                hint={t("dash.users.signedIn", { n: activity.dau_signed_in })}
              />
              <Kpi
                label={t("dash.users.wau")}
                value={num(activity.wau)}
                hint={t("dash.users.signedIn", { n: activity.wau_signed_in })}
              />
              <Kpi
                label={t("dash.users.mau")}
                value={num(activity.mau)}
                hint={t("dash.users.signedIn", { n: activity.mau_signed_in })}
              />
            </KpiGrid>
            <BarList
              caption={t("dash.users.visitors")}
              emptyLabel={t("dash.noActivity")}
              labelHeader={t("columns.day")}
              valueHeader={t("dash.users.visitors")}
              items={activity.daily_visitors
                .filter((day) => day.visitors > 0)
                .map((day) => ({
                  key: day.day,
                  label: day.day,
                  value: day.visitors,
                  display: num(day.visitors),
                }))}
            />
          </div>
        ) : (
          <p className="text-sm text-muted" data-testid="activity-disabled">
            {t("dash.users.activityOff")}
          </p>
        )}
      </TileShell>

      <TileShell title={t("dash.users.cohortsTitle")} subtitle={t("dash.users.cohortsHint")}>
        {data.cohorts.every((cohort) => cohort.size === 0) ? (
          <p className="text-sm text-muted">{t("dash.noActivity")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[28rem] text-sm">
              <caption className="sr-only">{t("dash.users.cohortsTitle")}</caption>
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th scope="col" className="py-1 pr-3 font-medium">
                    {t("dash.users.cohort")}
                  </th>
                  <th scope="col" className="py-1 pr-3 text-right font-medium">
                    {t("dash.users.cohortSize")}
                  </th>
                  {data.cohorts[0]?.retained.slice(1).map((_, index) => (
                    <th key={index} scope="col" className="py-1 pr-3 text-right font-medium">
                      {t("dash.users.monthN", { n: index + 1 })}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.cohorts.map((cohort) => (
                  <tr key={cohort.cohort} className="border-t border-border">
                    <th scope="row" className="py-1 pr-3 text-left font-normal">
                      {cohort.cohort}
                      {cohort.small_sample && cohort.size > 0 ? (
                        <span className="ml-1 text-xs text-muted">{t("dash.users.small")}</span>
                      ) : null}
                    </th>
                    <td className="py-1 pr-3 text-right font-mono text-xs">{num(cohort.size)}</td>
                    {cohort.retained_bps.slice(1).map((bps, index) => (
                      <td key={index} className="py-1 pr-3 text-right font-mono text-xs">
                        {cohort.retained[index + 1] === null ? "" : percent(bps)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </TileShell>
    </div>
  );
}

function GrowthTab({ data, locale }: { data: GrowthData; locale: string }) {
  const t = useTranslations("admin.analytics");
  const { num, percent, delta } = useFormat(locale);
  return (
    <div className="space-y-4">
      <TileShell title={t("dash.growth.title")} subtitle={t("dash.growth.hint")}>
        <KpiGrid>
          {GROWTH_KEYS.map((key) => (
            <Kpi
              key={key}
              label={t(`dash.growth.${key}`)}
              value={num(data.totals[key])}
              hint={delta(data.totals[key], data.previous_totals[key])}
            />
          ))}
          <Kpi label={t("dash.growth.checkoutToPaid")} value={percent(data.checkout_to_paid_bps)} />
        </KpiGrid>
      </TileShell>
      <TileShell title={t("dash.daily")}>
        <DailyTable
          caption={t("dash.daily")}
          rows={data.daily}
          columns={GROWTH_KEYS.map((key) => ({
            key,
            label: t(`dash.growth.${key}`),
            render: (row: GrowthData["daily"][number]) => num(row[key]),
          }))}
        />
      </TileShell>
    </div>
  );
}

function RevenueTab({ data, locale }: { data: RevenueData; locale: string }) {
  const t = useTranslations("admin.analytics");
  const { num, money, percent, delta } = useFormat(locale);
  const revenue = data.platform_revenue;
  const orders = data.orders;
  return (
    <div className="space-y-4">
      {!orders.payments_reconciled ? (
        <p className="rounded-md border border-danger/40 p-3 text-sm text-danger" role="alert">
          {t("overview.reconciliation.mismatch", { days: orders.payment_mismatch_days.join(", ") })}
        </p>
      ) : null}
      <TileShell title={t("dash.revenue.title")} subtitle={t("dash.revenue.hint")}>
        <KpiGrid>
          <Kpi
            label={t("dash.revenue.platformRevenue")}
            value={money(revenue.total_ngwee)}
            hint={delta(revenue.total_ngwee, data.previous_platform_revenue.total_ngwee)}
          />
          <Kpi label={t("dash.revenue.commission")} value={money(revenue.commission_ngwee)} />
          <Kpi label={t("dash.revenue.delivery")} value={money(revenue.delivery_ngwee)} />
          <Kpi
            label={t("dash.revenue.processingFees")}
            value={money(revenue.processing_fees_ngwee)}
            hint={t("dash.revenue.processingFeesHint")}
          />
        </KpiGrid>
      </TileShell>
      <TileShell title={t("dash.revenue.ordersTitle")} subtitle={t("dash.revenue.ordersHint")}>
        <KpiGrid>
          <Kpi
            label={t("dash.revenue.paidOrders")}
            value={num(orders.paid)}
            hint={delta(orders.paid, data.previous_orders.paid)}
          />
          <Kpi
            label={t("dash.revenue.paidOrderValue")}
            value={money(orders.paid_order_value_ngwee)}
            hint={t("dash.revenue.notRevenue")}
          />
          <Kpi
            label={t("dash.revenue.averagePaidOrder")}
            value={
              orders.average_paid_order_ngwee === null
                ? t("notAvailable")
                : money(orders.average_paid_order_ngwee)
            }
          />
          <Kpi label={t("dash.revenue.takeRate")} value={percent(data.take_rate_bps)} />
          <Kpi
            label={t("dash.revenue.cancelled")}
            value={num(orders.cancelled)}
            hint={t("dash.revenue.paidThenCancelled", { n: orders.paid_then_cancelled ?? 0 })}
          />
          <Kpi label={t("dash.revenue.placed")} value={num(orders.placed)} />
        </KpiGrid>
      </TileShell>
      <TileShell title={t("dash.revenue.refundsTitle")}>
        <KpiGrid>
          <Kpi label={t("dash.revenue.refundsRequested")} value={num(data.refunds.requested)} />
          <Kpi
            label={t("dash.revenue.refundsCompleted")}
            value={num(data.refunds.completed)}
            hint={money(data.refunds.completed_ngwee)}
          />
          <Kpi label={t("dash.revenue.refundsOpen")} value={num(data.refunds.open)} />
          <Kpi label={t("dash.revenue.refundsFailed")} value={num(data.refunds.failed)} />
        </KpiGrid>
      </TileShell>
      <TileShell title={t("dash.daily")}>
        <DailyTable
          caption={t("dash.daily")}
          rows={data.daily}
          columns={[
            { key: "p", label: t("dash.revenue.paidOrders"), render: (r) => num(r.orders_paid) },
            {
              key: "v",
              label: t("dash.revenue.paidOrderValue"),
              render: (r) => money(r.paid_order_value_ngwee),
            },
            {
              key: "c",
              label: t("dash.revenue.commission"),
              render: (r) => money(r.commission_ngwee),
            },
            {
              key: "d",
              label: t("dash.revenue.delivery"),
              render: (r) => money(r.delivery_ngwee),
            },
          ]}
        />
      </TileShell>
    </div>
  );
}

function VendorsTab({ data, locale }: { data: VendorsData; locale: string }) {
  const t = useTranslations("admin.analytics");
  const { num, money } = useFormat(locale);
  return (
    <div className="space-y-4">
      <TileShell title={t("dash.vendors.title")}>
        <KpiGrid>
          <Kpi label={t("dash.vendors.total")} value={num(data.vendors.total)} />
          <Kpi label={t("dash.vendors.active")} value={num(data.vendors.active)} />
          <Kpi label={t("dash.vendors.new")} value={num(data.vendors.new)} />
          <Kpi
            label={t("dash.vendors.selling")}
            value={num(data.vendors.selling)}
            hint={t("dash.vendors.sellingHint")}
          />
        </KpiGrid>
      </TileShell>
      <TileShell title={t("dash.vendors.kycTitle")} subtitle={t("dash.vendors.kycHint")}>
        <div className="space-y-3">
          <KpiGrid>
            <Kpi label={t("dash.vendors.kycSubmitted")} value={num(data.kyc.submitted)} />
            <Kpi label={t("dash.vendors.kycApproved")} value={num(data.kyc.approved)} />
            <Kpi label={t("dash.vendors.kycRejected")} value={num(data.kyc.rejected)} />
            <Kpi
              label={t("dash.vendors.kycDecisionTime")}
              value={
                data.kyc.avg_decision_hours === null
                  ? t("notAvailable")
                  : t("dash.vendors.hours", { n: data.kyc.avg_decision_hours })
              }
            />
          </KpiGrid>
          <BarList
            caption={t("dash.vendors.kycCurrent")}
            emptyLabel={t("dash.noActivity")}
            labelHeader={t("dash.vendors.status")}
            valueHeader={t("dash.vendors.count")}
            items={KYC_STATUSES.filter((status) => data.kyc.current[status] > 0).map((status) => ({
              key: status,
              label: t(`dash.kycStatus.${status}`),
              value: data.kyc.current[status],
              display: num(data.kyc.current[status]),
            }))}
          />
        </div>
      </TileShell>
      <TileShell title={t("dash.vendors.statusTitle")}>
        <BarList
          caption={t("dash.vendors.statusTitle")}
          emptyLabel={t("dash.noActivity")}
          labelHeader={t("dash.vendors.status")}
          valueHeader={t("dash.vendors.count")}
          items={VENDOR_STATUSES.filter((status) => data.vendors.by_status[status] > 0).map(
            (status) => ({
              key: status,
              label: t(`dash.vendorStatus.${status}`),
              value: data.vendors.by_status[status],
              display: num(data.vendors.by_status[status]),
            }),
          )}
        />
      </TileShell>
      <TileShell title={t("dash.vendors.topTitle")} subtitle={t("dash.vendors.topHint")}>
        <div className="space-y-2">
          <p className="text-xs text-muted">
            {data.ratings.reviews === 0 || data.ratings.avg_x100 === null
              ? t("dash.vendors.noReviews")
              : t("dash.vendors.ratings", {
                  n: data.ratings.reviews,
                  avg: ratingText(data.ratings.avg_x100),
                })}
          </p>
          {!data.finance_visible ? (
            <p className="text-xs text-muted">{t("financeWithheld")}</p>
          ) : null}
          {data.top.length === 0 ? (
            <p className="text-sm text-muted">{t("dash.noActivity")}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[24rem] text-sm">
                <caption className="sr-only">{t("dash.vendors.topTitle")}</caption>
                <thead>
                  <tr className="text-left text-xs text-muted">
                    <th scope="col" className="py-1 pr-3 font-medium">
                      {t("dash.vendors.vendor")}
                    </th>
                    <th scope="col" className="py-1 pr-3 text-right font-medium">
                      {t("dash.revenue.paidOrders")}
                    </th>
                    {data.finance_visible ? (
                      <th scope="col" className="py-1 pr-3 text-right font-medium">
                        {t("dash.vendors.itemSales")}
                      </th>
                    ) : null}
                    <th scope="col" className="py-1 pr-3 text-right font-medium">
                      {t("dash.vendors.rating")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.top.map((row) => (
                    <tr key={row.vendor_id} className="border-t border-border">
                      <th scope="row" className="py-1 pr-3 text-left font-normal">
                        {row.name}
                      </th>
                      <td className="py-1 pr-3 text-right font-mono text-xs">
                        {num(row.paid_orders)}
                      </td>
                      {data.finance_visible ? (
                        <td className="py-1 pr-3 text-right font-mono text-xs">
                          {row.item_sales_ngwee === null ? "" : money(row.item_sales_ngwee)}
                        </td>
                      ) : null}
                      <td className="py-1 pr-3 text-right font-mono text-xs">
                        {row.rating_avg_x100 === null
                          ? t("notAvailable")
                          : t("dash.vendors.ratingCell", {
                              avg: ratingText(row.rating_avg_x100),
                              n: row.rating_count,
                            })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </TileShell>
    </div>
  );
}

function ServicesEventsTab({ data, locale }: { data: ServicesEventsData; locale: string }) {
  const t = useTranslations("admin.analytics");
  const { num, percent } = useFormat(locale);
  const s = data.services;
  const e = data.events;
  return (
    <div className="space-y-4">
      <TileShell title={t("dash.services.title")} subtitle={t("dash.services.hint")}>
        <KpiGrid>
          <Kpi label={t("dash.services.activeListings")} value={num(s.active_listings)} />
          <Kpi
            label={t("dash.services.jobsPosted")}
            value={num(s.jobs_posted)}
            hint={t("dash.services.quotes", {
              submitted: s.quotes_submitted,
              accepted: s.quotes_accepted,
            })}
          />
          <Kpi
            label={t("dash.services.rfqOpened")}
            value={num(s.rfq_opened)}
            hint={t("dash.services.rfqProgress", {
              quoted: s.rfq_quoted,
              accepted: s.rfq_accepted,
            })}
          />
          <Kpi
            label={t("dash.services.bookings")}
            value={num(s.bookings)}
            hint={t("dash.services.bookingsPaid", { n: s.bookings_paid })}
          />
        </KpiGrid>
      </TileShell>
      <TileShell title={t("dash.events.title")} subtitle={t("dash.events.hint")}>
        <KpiGrid>
          <Kpi label={t("dash.events.published")} value={num(e.published)} />
          <Kpi label={t("dash.events.instances")} value={num(e.instances)} />
          <Kpi label={t("dash.events.ticketsSold")} value={num(e.tickets_sold)} />
          <Kpi
            label={t("dash.events.checkIns")}
            value={num(e.check_ins)}
            hint={t("dash.events.checkInRate", { rate: percent(e.check_in_rate_bps) })}
          />
        </KpiGrid>
      </TileShell>
      <TileShell title={t("dash.daily")}>
        <DailyTable
          caption={t("dash.daily")}
          rows={data.daily}
          columns={[
            { key: "j", label: t("dash.services.jobsPosted"), render: (r) => num(r.jobs_posted) },
            { key: "r", label: t("dash.services.rfqOpened"), render: (r) => num(r.rfq_opened) },
            { key: "t", label: t("dash.events.ticketsSold"), render: (r) => num(r.tickets_sold) },
            { key: "c", label: t("dash.events.checkIns"), render: (r) => num(r.check_ins) },
          ]}
        />
      </TileShell>
    </div>
  );
}
