"use client";

import { formatK } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { Skeleton } from "@vergeo/ui/src/skeleton";
import { orderStatusTone, StatusChip } from "@vergeo/ui/src/status-chip";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { type OrderSearchItem, ordersApi } from "./api";

const STATUS_VALUES: string[] = [
  "placed",
  "confirmed",
  "processing",
  "ready",
  "shipped",
  "delivered",
  "completed",
  "cancelled",
];

export const ORDERS_PAGE_SIZE = 50;

type OrderSearchProps = {
  locale: string;
};

export function shortOrderRef(id: string): string {
  return `#${id.slice(0, 8).toUpperCase()}`;
}

type Filters = { orderId: string; phone: string; vendor: string; status: string };

export function orderSearchParams(filters: Filters, before: string | null): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.orderId.trim()) params.set("order_id", filters.orderId.trim());
  if (filters.phone.trim()) params.set("phone", filters.phone.trim());
  if (filters.vendor.trim()) params.set("vendor", filters.vendor.trim());
  if (filters.status.trim()) params.set("status", filters.status.trim());
  if (before) params.set("before", before);
  return params;
}

/** Only the newest-first lists (no filter, or status only) can page; the others are capped. */
function canPage(filters: Filters): boolean {
  return !filters.orderId.trim() && !filters.phone.trim() && !filters.vendor.trim();
}

export function OrderSearch({ locale }: OrderSearchProps) {
  const t = useTranslations("admin.orders.search");
  const tEmpty = useTranslations("admin.boards.states.orders");
  const router = useRouter();
  const [orderId, setOrderId] = useState("");
  const [phone, setPhone] = useState("");
  const [vendor, setVendor] = useState("");
  const [status, setStatus] = useState("");
  const [results, setResults] = useState<OrderSearchItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [applied, setApplied] = useState<Filters | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const generation = useRef(0);

  const runSearch = useCallback(
    async (override?: Partial<Filters>, before: string | null = null) => {
      const filters: Filters = { orderId, phone, vendor, status, ...override };
      const current = ++generation.current;
      if (before) setLoadingMore(true);
      else setLoading(true);
      setError(null);
      setSearched(true);
      try {
        const params = orderSearchParams(filters, before);
        const query = params.toString();
        const data = await ordersApi.request<OrderSearchItem[]>(
          `/admin/orders/search${query ? `?${query}` : ""}`,
        );
        if (current !== generation.current) return;
        const page = Array.isArray(data) ? data : [];
        setResults((previous) => (before ? [...previous, ...page] : page));
        setApplied(filters);
        setHasMore(canPage(filters) && page.length >= ORDERS_PAGE_SIZE);
      } catch {
        if (current !== generation.current) return;
        setError(t("error"));
        if (!before) setResults([]);
        setHasMore(false);
      } finally {
        if (current === generation.current) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [orderId, phone, vendor, status, t],
  );

  // Deep link from the Today board: /orders?status=placed runs that search once.
  // Without one the page opens on the newest orders.
  const initialised = useRef(false);
  useEffect(() => {
    if (initialised.current) return;
    initialised.current = true;
    const wanted = new URLSearchParams(window.location.search).get("status");
    if (wanted && STATUS_VALUES.includes(wanted)) {
      setStatus(wanted);
      void runSearch({ status: wanted });
    } else {
      void runSearch({ orderId: "", phone: "", vendor: "", status: "" });
    }
  }, [runSearch]);

  const isRecent =
    applied !== null &&
    !applied.orderId.trim() &&
    !applied.phone.trim() &&
    !applied.vendor.trim() &&
    !applied.status.trim();
  const dateFormat = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" });
  const customerLabel = (item: OrderSearchItem) =>
    item.customer_display_name || item.customer_phone || t("unknownCustomer");

  return (
    <div className="space-y-4">
      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(event) => {
          event.preventDefault();
          void runSearch();
        }}
      >
        <label className="space-y-1 text-sm">
          <span className="text-muted">{t("orderId")}</span>
          <input
            className="min-h-11 w-full rounded-md border border-border bg-surface px-3"
            value={orderId}
            onChange={(event) => setOrderId(event.target.value)}
            placeholder={t("orderIdPlaceholder")}
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-muted">{t("phone")}</span>
          <input
            className="min-h-11 w-full rounded-md border border-border bg-surface px-3"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder={t("phonePlaceholder")}
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-muted">{t("vendor")}</span>
          <input
            className="min-h-11 w-full rounded-md border border-border bg-surface px-3"
            value={vendor}
            onChange={(event) => setVendor(event.target.value)}
            placeholder={t("vendorPlaceholder")}
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-muted">{t("status")}</span>
          <select
            className="min-h-11 w-full rounded-md border border-border bg-surface px-3"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">{t("statusAny")}</option>
            {(
              [
                "placed",
                "confirmed",
                "processing",
                "ready",
                "shipped",
                "delivered",
                "completed",
                "cancelled",
              ] as const
            ).map((value) => (
              <option key={value} value={value}>
                {t(`statuses.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap items-center gap-3 sm:col-span-2 xl:col-span-4">
          <button
            type="submit"
            className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-[var(--primary-btn-fg)] disabled:opacity-60"
            disabled={loading}
          >
            {loading ? t("searching") : t("submit")}
          </button>
          {!isRecent ? (
            <button
              type="button"
              className="min-h-11 text-sm font-medium text-primary underline"
              disabled={loading}
              onClick={() => {
                setOrderId("");
                setPhone("");
                setVendor("");
                setStatus("");
                void runSearch({ orderId: "", phone: "", vendor: "", status: "" });
              }}
            >
              {t("showRecent")}
            </button>
          ) : null}
        </div>
      </form>

      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}

      {loading ? (
        <div className="space-y-3" data-testid="orders-search-loading" aria-busy="true">
          <p className="sr-only">{t("searching")}</p>
          <Skeleton height="4rem" />
          <Skeleton height="4rem" />
          <Skeleton height="4rem" />
          <Skeleton height="4rem" />
        </div>
      ) : null}

      {!loading && results.length > 0 ? (
        <h2 className="text-sm font-semibold text-text" data-testid="orders-results-heading">
          {isRecent ? t("recentHeading") : t("resultsHeading", { count: results.length })}
        </h2>
      ) : null}

      {searched && !loading && !error && results.length === 0 ? (
        <EmptyState
          data-testid="orders-search-empty"
          title={tEmpty("emptyTitle")}
          body={tEmpty("emptyBody")}
        />
      ) : null}

      {!loading && results.length > 0 ? (
        <ul className="space-y-3 md:hidden" data-testid="orders-results-cards">
          {results.map((item) => (
            <li key={item.id} className="space-y-2 rounded-lg border border-border bg-surface p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium text-text">{customerLabel(item)}</p>
                  <p className="text-xs text-muted">
                    {shortOrderRef(item.id)} · {item.vendor_display_name}
                  </p>
                  <p className="text-xs text-muted">
                    {formatK(item.total_ngwee ?? 0)} ·{" "}
                    {dateFormat.format(new Date(item.created_at))}
                  </p>
                </div>
                <StatusChip
                  tone={orderStatusTone(item.status)}
                  label={t(`statuses.${item.status}`)}
                />
              </div>
              <button
                type="button"
                className="inline-flex min-h-11 items-center rounded-md border border-primary px-4 text-sm font-medium text-primary"
                onClick={() => router.push(`/${locale}/orders/${item.id}`)}
              >
                {t("open")}
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {!loading && results.length > 0 ? (
        <div className="hidden overflow-x-auto rounded-lg border border-border bg-surface md:block">
          <table className="min-w-full text-left text-sm" data-testid="orders-results-table">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
                <th className="px-3 py-3 font-medium">{t("columns.order")}</th>
                <th className="px-3 py-3 font-medium">{t("columns.customer")}</th>
                <th className="px-3 py-3 font-medium">{t("columns.vendor")}</th>
                <th className="px-3 py-3 font-medium">{t("columns.status")}</th>
                <th className="px-3 py-3 text-right font-medium">{t("columns.total")}</th>
                <th className="px-3 py-3 font-medium">{t("columns.date")}</th>
                <th className="px-3 py-3 font-medium">
                  <span className="sr-only">{t("open")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {results.map((item) => (
                <tr key={item.id} className="border-b border-border hover:bg-bg-2">
                  <td className="px-3 py-3 font-mono text-xs" title={item.id}>
                    {shortOrderRef(item.id)}
                  </td>
                  <td className="px-3 py-3">
                    <div className="font-medium">{customerLabel(item)}</div>
                    {item.customer_display_name && item.customer_phone ? (
                      <div className="text-xs text-muted">{item.customer_phone}</div>
                    ) : null}
                  </td>
                  <td className="px-3 py-3">
                    <div className="font-medium">{item.vendor_display_name}</div>
                    <div className="text-xs text-muted">{item.vendor_slug}</div>
                  </td>
                  <td className="px-3 py-3">
                    <StatusChip
                      tone={orderStatusTone(item.status)}
                      label={t(`statuses.${item.status}`)}
                    />
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums">
                    {formatK(item.total_ngwee ?? 0)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 text-muted">
                    {dateFormat.format(new Date(item.created_at))}
                  </td>
                  <td className="px-3 py-3 text-right">
                    <button
                      type="button"
                      className="inline-flex min-h-11 items-center rounded-md border border-primary px-4 text-sm font-medium text-primary"
                      onClick={() => router.push(`/${locale}/orders/${item.id}`)}
                    >
                      {t("open")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {!loading && hasMore && results.length > 0 ? (
        <button
          type="button"
          data-testid="orders-load-more"
          className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm font-medium"
          disabled={loadingMore}
          onClick={() =>
            applied && void runSearch(applied, results[results.length - 1]?.created_at ?? null)
          }
        >
          {loadingMore ? t("searching") : t("loadMore")}
        </button>
      ) : null}
    </div>
  );
}
