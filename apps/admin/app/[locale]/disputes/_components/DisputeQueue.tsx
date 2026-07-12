"use client";

import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { type DisputeQueueItem, type QueueSort, disputesApi } from "./api";
import { DisputeSlaBadge } from "./DisputeSlaBadge";

type DisputeQueueProps = {
  locale: string;
};

export function DisputeQueue({ locale }: DisputeQueueProps) {
  const t = useTranslations("admin.disputes.queue");
  const [items, setItems] = useState<DisputeQueueItem[]>([]);
  const [sort, setSort] = useState<QueueSort>("age");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await disputesApi.request<DisputeQueueItem[]>(`/admin/disputes?sort=${sort}`);
      setItems(data);
    } catch {
      setError(t("error"));
    } finally {
      setLoading(false);
    }
  }, [sort, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return <p className="text-sm text-muted">{t("loading")}</p>;
  }

  if (error) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-danger">{error}</p>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
          onClick={() => void load()}
        >
          {t("retry")}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm text-muted" htmlFor="dispute-sort">
          {t("sortLabel")}
        </label>
        <select
          id="dispute-sort"
          className="min-h-11 rounded-md border border-border px-2 text-sm"
          value={sort}
          onChange={(event) => setSort(event.target.value as QueueSort)}
        >
          <option value="age">{t("sortAge")}</option>
          <option value="value">{t("sortValue")}</option>
        </select>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
                <th className="px-2 py-3 font-medium">{t("order")}</th>
                <th className="px-2 py-3 font-medium">{t("vendor")}</th>
                <th className="px-2 py-3 font-medium">{t("value")}</th>
                <th className="px-2 py-3 font-medium">{t("opened")}</th>
                <th className="px-2 py-3 font-medium">{t("slaColumn")}</th>
                <th className="px-2 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-b border-border">
                  <td className="px-2 py-3 font-mono text-xs text-text">
                    {t("orderIdShort", { id: item.order_id.slice(0, 8) })}
                  </td>
                  <td className="px-2 py-3">
                    <div className="font-medium text-text">{item.vendor_display_name}</div>
                    <div className="text-xs text-muted">{item.customer_phone ?? "—"}</div>
                  </td>
                  <td className="px-2 py-3 font-mono text-text">
                    {formatK(item.order_total_ngwee)}
                  </td>
                  <td className="px-2 py-3 text-muted">
                    {new Date(item.created_at).toLocaleString(locale)}
                  </td>
                  <td className="px-2 py-3">
                    <DisputeSlaBadge badge={item.sla_badge} />
                  </td>
                  <td className="px-2 py-3 text-right">
                    <a
                      className="inline-flex min-h-11 items-center rounded-md border border-primary px-4 text-sm font-medium text-primary"
                      href={`/${locale}/disputes/${item.id}`}
                    >
                      {t("review")}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
