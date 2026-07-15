"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import {
  type BusinessBuyer,
  type StatusFilter,
  listBusinessBuyers,
  rejectBusinessBuyer,
  verifyBusinessBuyer,
} from "./api";

type BusinessQueueProps = {
  locale: string;
};

const FILTERS: StatusFilter[] = ["pending", "verified", "rejected", "suspended", "all"];

export function BusinessQueue({ locale }: BusinessQueueProps) {
  const t = useTranslations("admin.business.queue");
  const [filter, setFilter] = useState<StatusFilter>("pending");
  const [items, setItems] = useState<BusinessBuyer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await listBusinessBuyers(filter));
    } catch {
      setError(t("error"));
    } finally {
      setLoading(false);
    }
  }, [filter, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onVerify = useCallback(
    async (id: string) => {
      setBusyId(id);
      setError(null);
      try {
        await verifyBusinessBuyer(id);
        await load();
      } catch {
        setError(t("actionError"));
      } finally {
        setBusyId(null);
      }
    },
    [load, t],
  );

  const onReject = useCallback(
    async (id: string) => {
      if (rejectReason.trim().length < 3) {
        setError(t("reasonRequired"));
        return;
      }
      setBusyId(id);
      setError(null);
      try {
        await rejectBusinessBuyer(id, rejectReason.trim());
        setRejectingId(null);
        setRejectReason("");
        await load();
      } catch {
        setError(t("actionError"));
      } finally {
        setBusyId(null);
      }
    },
    [load, rejectReason, t],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="business-filter" className="text-sm text-muted">
          {t("filterLabel")}
        </label>
        <select
          id="business-filter"
          value={filter}
          onChange={(event) => setFilter(event.target.value as StatusFilter)}
          className="h-11 rounded-md border border-border bg-surface px-3 text-sm text-text"
        >
          {FILTERS.map((value) => (
            <option key={value} value={value}>
              {t(`filter.${value}`)}
            </option>
          ))}
        </select>
      </div>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      {loading ? (
        <p className="text-sm text-muted">{t("loading")}</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
                <th className="px-2 py-3 font-medium">{t("business")}</th>
                <th className="px-2 py-3 font-medium">{t("registration")}</th>
                <th className="px-2 py-3 font-medium">{t("submitted")}</th>
                <th className="px-2 py-3 font-medium">{t("statusColumn")}</th>
                <th className="px-2 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-b border-border align-top">
                  <td className="px-2 py-3">
                    <div className="font-medium text-text">{item.legal_name}</div>
                    {item.tpin ? (
                      <div className="text-xs text-muted">{t("tpin", { tpin: item.tpin })}</div>
                    ) : null}
                  </td>
                  <td className="px-2 py-3 text-muted">{item.registration_no}</td>
                  <td className="px-2 py-3 text-muted">
                    {item.created_at ? new Date(item.created_at).toLocaleString(locale) : "—"}
                  </td>
                  <td className="px-2 py-3">
                    <span className="text-text">{t(`status.${item.status}`)}</span>
                  </td>
                  <td className="px-2 py-3 text-right">
                    {item.status === "pending" ? (
                      rejectingId === item.id ? (
                        <div className="flex flex-col items-end gap-2">
                          <input
                            type="text"
                            value={rejectReason}
                            onChange={(event) => setRejectReason(event.target.value)}
                            placeholder={t("reasonPlaceholder")}
                            className="h-11 w-full max-w-xs rounded-md border border-border bg-surface px-3 text-sm text-text"
                            maxLength={1000}
                          />
                          <div className="flex gap-2">
                            <button
                              type="button"
                              disabled={busyId === item.id}
                              onClick={() => void onReject(item.id)}
                              className="inline-flex min-h-11 items-center rounded-md border border-danger px-4 text-sm font-medium text-danger disabled:opacity-50"
                            >
                              {t("confirmReject")}
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setRejectingId(null);
                                setRejectReason("");
                              }}
                              className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
                            >
                              {t("cancel")}
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            disabled={busyId === item.id}
                            onClick={() => void onVerify(item.id)}
                            className="inline-flex min-h-11 items-center rounded-md border border-primary px-4 text-sm font-medium text-primary disabled:opacity-50"
                          >
                            {t("verify")}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setRejectingId(item.id);
                              setRejectReason("");
                              setError(null);
                            }}
                            className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
                          >
                            {t("reject")}
                          </button>
                        </div>
                      )
                    ) : item.reviewer_notes ? (
                      <span className="text-xs text-muted">{item.reviewer_notes}</span>
                    ) : null}
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
