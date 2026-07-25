"use client";

import { formatK } from "@vergeo/i18n";
import { Skeleton } from "@vergeo/ui/src/skeleton";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";

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
  const [permissionDenied, setPermissionDenied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      const data = await disputesApi.request<DisputeQueueItem[]>(`/admin/disputes?sort=${sort}`);
      setItems(data);
    } catch (err) {
      const failure = resolveQueueLoadFailure(err);
      setPermissionDenied(failure.permissionDenied);
      setError(t(failure.messageKey));
    } finally {
      setLoading(false);
    }
  }, [sort, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <div className="space-y-3" data-testid="disputes-queue-loading" aria-busy="true">
        <p className="sr-only">{t("loading")}</p>
        <Skeleton height="2.5rem" />
        <Skeleton height="4rem" />
        <Skeleton height="4rem" />
      </div>
    );
  }

  if (error) {
    return (
      <AdminLoadFailure
        permissionDenied={permissionDenied}
        message={error}
        hint={permissionDenied ? t("permissionDeniedHint") : undefined}
        retryLabel={t("retry")}
        onRetry={() => void load()}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm text-text-2" htmlFor="dispute-sort">
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
        <p className="text-sm text-text-2">{t("empty")}</p>
      ) : (
        <>
          <ul className="space-y-3 md:hidden" data-testid="disputes-queue-cards">
            {items.map((item) => (
              <li key={item.id} className="rounded-lg border border-border bg-surface p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 space-y-1">
                    <p className="font-medium text-text">{item.vendor_display_name}</p>
                    <p className="font-mono text-xs text-text-2">
                      {t("orderIdShort", { id: item.order_id.slice(0, 8) })}
                    </p>
                    <p className="text-xs text-text-3">{item.customer_phone ?? "—"}</p>
                    <p className="font-mono text-sm text-text">{formatK(item.order_total_ngwee)}</p>
                    <p className="text-xs text-text-3">
                      {new Date(item.created_at).toLocaleString(locale)}
                    </p>
                  </div>
                  <DisputeSlaBadge badge={item.sla_badge} />
                </div>
                <a
                  className="mt-3 inline-flex min-h-11 items-center rounded-md border border-primary px-4 text-sm font-medium text-primary"
                  href={`/${locale}/disputes/${item.id}`}
                >
                  {t("review")}
                </a>
              </li>
            ))}
          </ul>

          <div className="hidden overflow-x-auto md:block" data-testid="disputes-queue-table">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-text-3">
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
                  <tr key={item.id} className="border-b border-border hover:bg-bg-2">
                    <td className="px-2 py-3 font-mono text-xs text-text">
                      {t("orderIdShort", { id: item.order_id.slice(0, 8) })}
                    </td>
                    <td className="px-2 py-3">
                      <div className="font-medium text-text">{item.vendor_display_name}</div>
                      <div className="text-xs text-text-3">{item.customer_phone ?? "—"}</div>
                    </td>
                    <td className="px-2 py-3 font-mono text-text">
                      {formatK(item.order_total_ngwee)}
                    </td>
                    <td className="px-2 py-3 text-text-2">
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
        </>
      )}
    </div>
  );
}
