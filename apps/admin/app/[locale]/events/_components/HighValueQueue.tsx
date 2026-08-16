"use client";

import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { listHighValueQueue, verifyHighValueEvent, type HighValueQueueItem } from "./api";

export function HighValueQueue() {
  const t = useTranslations("admin.events.queue");
  const [items, setItems] = useState<HighValueQueueItem[]>([]);
  const [threshold, setThreshold] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await listHighValueQueue();
      setItems(payload.items);
      setThreshold(payload.threshold_ngwee);
    } catch {
      setError(t("error"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onVerify = useCallback(
    async (eventId: string) => {
      setBusyId(eventId);
      setError(null);
      try {
        await verifyHighValueEvent(eventId);
        await load();
      } catch {
        setError(t("actionError"));
      } finally {
        setBusyId(null);
      }
    },
    [load, t],
  );

  if (loading) {
    return <p className="text-sm text-muted">{t("loading")}</p>;
  }

  return (
    <div className="space-y-3">
      {threshold !== null ? (
        <p className="text-sm text-muted">{t("threshold", { amount: formatK(threshold) })}</p>
      ) : null}
      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
      {items.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="space-y-3">
          {items.map((item) => (
            <li
              key={item.event_id}
              className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <p className="font-medium">{item.title}</p>
                <p className="text-sm text-muted">{t("status", { status: item.status })}</p>
                <p className="text-sm text-muted">
                  {t("projected", { amount: formatK(item.projected_gmv_ngwee) })}
                </p>
              </div>
              <button
                type="button"
                className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-4 text-sm font-semibold text-[var(--primary-btn-fg)] disabled:opacity-50"
                disabled={busyId === item.event_id}
                onClick={() => {
                  void onVerify(item.event_id);
                }}
              >
                {t("verify")}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
