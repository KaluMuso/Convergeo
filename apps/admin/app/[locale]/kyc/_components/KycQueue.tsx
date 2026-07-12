"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { type KycQueueItem, kycApi } from "./api";
import { SlaBadge } from "./SlaBadge";

type KycQueueProps = {
  locale: string;
};

export function KycQueue({ locale }: KycQueueProps) {
  const t = useTranslations("admin.kyc.queue");
  const [items, setItems] = useState<KycQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await kycApi.request<KycQueueItem[]>("/admin/kyc");
      setItems(data);
    } catch {
      setError(t("error"));
    } finally {
      setLoading(false);
    }
  }, [t]);

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

  if (items.length === 0) {
    return <p className="text-sm text-muted">{t("empty")}</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead>
          <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
            <th className="px-2 py-3 font-medium">{t("vendor")}</th>
            <th className="px-2 py-3 font-medium">{t("submitted")}</th>
            <th className="px-2 py-3 font-medium">{t("slaColumn")}</th>
            <th className="px-2 py-3 font-medium" />
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className="border-b border-border">
              <td className="px-2 py-3">
                <div className="font-medium text-text">{item.vendor_display_name}</div>
                <div className="text-xs text-muted">{t("tier", { tier: item.tier })}</div>
              </td>
              <td className="px-2 py-3 text-muted">
                {new Date(item.updated_at).toLocaleString(locale)}
              </td>
              <td className="px-2 py-3">
                <SlaBadge badge={item.sla_badge} />
              </td>
              <td className="px-2 py-3 text-right">
                <a
                  className="inline-flex min-h-11 items-center rounded-md border border-primary px-4 text-sm font-medium text-primary"
                  href={`/${locale}/kyc/${item.id}`}
                >
                  {t("review")}
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
