"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";

import { type VendorQueueItem, kycApi } from "./api";
import { KycReviewDialog } from "./KycReviewDialog";
import { SlaBadge } from "./SlaBadge";

type KycQueueProps = {
  locale: string;
};

export function KycQueue({ locale }: KycQueueProps) {
  const t = useTranslations("admin.kyc.queue");
  const [items, setItems] = useState<VendorQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [selected, setSelected] = useState<VendorQueueItem | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      const data = await kycApi.request<VendorQueueItem[]>("/admin/vendors?status=pending");
      setItems(data);
    } catch (err) {
      const failure = resolveQueueLoadFailure(err);
      setPermissionDenied(failure.permissionDenied);
      setError(t(failure.messageKey));
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
    <div className="space-y-3">
      {message ? <p className="text-sm text-success">{message}</p> : null}
      {items.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
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
                <tr key={item.vendor_id} className="border-b border-border hover:bg-bg-2">
                  <td className="px-2 py-3">
                    <div className="font-medium text-text">{item.display_name}</div>
                    <div className="text-xs text-muted">
                      {item.tier != null ? t("tier", { tier: item.tier }) : item.slug}
                    </div>
                  </td>
                  <td className="px-2 py-3 text-muted">
                    {new Date(item.updated_at).toLocaleString(locale)}
                  </td>
                  <td className="px-2 py-3">
                    {item.sla_badge ? <SlaBadge badge={item.sla_badge} /> : "—"}
                  </td>
                  <td className="px-2 py-3 text-right">
                    <button
                      type="button"
                      className="inline-flex min-h-11 items-center rounded-md border border-primary px-4 text-sm font-medium text-primary disabled:opacity-50"
                      disabled={!item.kyc_record_id}
                      onClick={() => setSelected(item)}
                    >
                      {t("review")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected ? (
        <KycReviewDialog
          item={selected}
          onClose={() => setSelected(null)}
          onComplete={() => {
            setSelected(null);
            setMessage(t("dialog.success"));
            void load();
          }}
        />
      ) : null}
    </div>
  );
}
