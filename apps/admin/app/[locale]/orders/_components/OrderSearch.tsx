"use client";

import { orderStatusTone, StatusChip } from "@vergeo/ui/src/status-chip";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { EmptyBlock, LoadingBlock } from "../../_components/StateBlocks";

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

type OrderSearchProps = {
  locale: string;
};

export function OrderSearch({ locale }: OrderSearchProps) {
  const t = useTranslations("admin.orders.search");
  const router = useRouter();
  const [orderId, setOrderId] = useState("");
  const [phone, setPhone] = useState("");
  const [vendor, setVendor] = useState("");
  const [status, setStatus] = useState("");
  const [results, setResults] = useState<OrderSearchItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const runSearch = useCallback(
    async (override?: { status?: string }) => {
      const effectiveStatus = override?.status ?? status;
      if (!orderId && !phone && !vendor && !effectiveStatus) {
        setError(t("needFilter"));
        return;
      }
      setLoading(true);
      setError(null);
      setSearched(true);
      try {
        const params = new URLSearchParams();
        if (orderId.trim()) params.set("order_id", orderId.trim());
        if (phone.trim()) params.set("phone", phone.trim());
        if (vendor.trim()) params.set("vendor", vendor.trim());
        if (effectiveStatus.trim()) params.set("status", effectiveStatus.trim());
        const data = await ordersApi.request<OrderSearchItem[]>(
          `/admin/orders/search?${params.toString()}`,
        );
        setResults(data);
      } catch {
        setError(t("error"));
        setResults([]);
      } finally {
        setLoading(false);
      }
    },
    [orderId, phone, vendor, status, t],
  );

  // Deep link from the Today board: /orders?status=placed runs that search once.
  const deepLinked = useRef(false);
  useEffect(() => {
    if (deepLinked.current) return;
    deepLinked.current = true;
    const wanted = new URLSearchParams(window.location.search).get("status");
    if (wanted && STATUS_VALUES.includes(wanted)) {
      setStatus(wanted);
      void runSearch({ status: wanted });
    }
  }, [runSearch]);

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
            className="min-h-11 w-full rounded-md border border-border px-3"
            value={orderId}
            onChange={(event) => setOrderId(event.target.value)}
            placeholder={t("orderIdPlaceholder")}
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-muted">{t("phone")}</span>
          <input
            className="min-h-11 w-full rounded-md border border-border px-3"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder={t("phonePlaceholder")}
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-muted">{t("vendor")}</span>
          <input
            className="min-h-11 w-full rounded-md border border-border px-3"
            value={vendor}
            onChange={(event) => setVendor(event.target.value)}
            placeholder={t("vendorPlaceholder")}
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-muted">{t("status")}</span>
          <select
            className="min-h-11 w-full rounded-md border border-border px-3"
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
        <div className="sm:col-span-2">
          <button
            type="submit"
            className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-[var(--primary-btn-fg)] disabled:opacity-60"
            disabled={loading}
          >
            {loading ? t("searching") : t("submit")}
          </button>
        </div>
      </form>

      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}

      {loading ? <LoadingBlock label={t("searching")} rows={3} /> : null}

      {searched && !loading && !error && results.length === 0 ? (
        <EmptyBlock title={t("empty")} body={t("emptyHint")} />
      ) : null}

      {results.length > 0 ? (
        <ul className="space-y-3 md:hidden" data-testid="orders-results-cards">
          {results.map((item) => (
            <li key={item.id} className="space-y-2 rounded-lg border border-border bg-surface p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium text-text">{item.vendor_display_name}</p>
                  <p className="truncate font-mono text-xs text-muted">{item.id}</p>
                  <p className="text-xs text-muted">{item.customer_phone ?? "—"}</p>
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

      {results.length > 0 ? (
        <div className="hidden overflow-x-auto md:block">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
                <th className="px-2 py-3 font-medium">{t("columns.order")}</th>
                <th className="px-2 py-3 font-medium">{t("columns.vendor")}</th>
                <th className="px-2 py-3 font-medium">{t("columns.phone")}</th>
                <th className="px-2 py-3 font-medium">{t("columns.status")}</th>
                <th className="px-2 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {results.map((item) => (
                <tr key={item.id} className="border-b border-border hover:bg-bg-2">
                  <td className="px-2 py-3 font-mono text-xs">{item.id}</td>
                  <td className="px-2 py-3">
                    <div className="font-medium">{item.vendor_display_name}</div>
                    <div className="text-xs text-muted">{item.vendor_slug}</div>
                  </td>
                  <td className="px-2 py-3 text-muted">{item.customer_phone ?? "—"}</td>
                  <td className="px-2 py-3">
                    <StatusChip
                      tone={orderStatusTone(item.status)}
                      label={t(`statuses.${item.status}`)}
                    />
                  </td>
                  <td className="px-2 py-3 text-right">
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
    </div>
  );
}
