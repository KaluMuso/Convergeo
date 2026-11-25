"use client";

import { IconTile } from "@vergeo/ui/src/icon-tile";
import { LcStore } from "@vergeo/ui/src/lucide-icons";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";
import { EmptyBlock, LoadingBlock } from "../../_components/StateBlocks";

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
    return <LoadingBlock label={t("loading")} />;
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
      {message ? (
        <p role="status" className="text-sm text-success">
          {message}
        </p>
      ) : null}
      {items.length === 0 ? (
        <EmptyBlock illustration="verify-id" title={t("empty")} body={t("emptyHint")} />
      ) : (
        <>
          <ul
            className="m-0 flex list-none flex-col gap-3 p-0 sm:hidden"
            data-testid="kyc-queue-cards"
          >
            {items.map((item) => (
              <li
                key={item.vendor_id}
                className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-3"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <IconTile hue="teal" size={40} aria-hidden>
                    <LcStore className="size-5" duotone />
                  </IconTile>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium text-text">{item.display_name}</div>
                    <div className="truncate text-xs text-muted">
                      {item.tier != null ? t("tier", { tier: item.tier }) : item.slug}
                    </div>
                  </div>
                  {item.sla_badge ? <SlaBadge badge={item.sla_badge} /> : null}
                </div>
                <div className="text-xs text-muted">
                  {t("submitted")}: {new Date(item.updated_at).toLocaleString(locale)}
                </div>
                <button
                  type="button"
                  className="inline-flex min-h-11 w-full items-center justify-center rounded-md border border-primary px-4 text-sm font-medium text-primary disabled:opacity-50"
                  disabled={!item.kyc_record_id}
                  onClick={() => setSelected(item)}
                >
                  {t("review")}
                </button>
              </li>
            ))}
          </ul>
          <div className="hidden overflow-x-auto sm:block">
            <table className="admin-data-table min-w-full">
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
                      <div className="flex min-w-0 items-center gap-2">
                        <IconTile hue="teal" size={40} aria-hidden>
                          <LcStore className="size-5" duotone />
                        </IconTile>
                        <div className="min-w-0">
                          <div className="truncate font-medium text-text">{item.display_name}</div>
                          <div className="truncate text-xs text-muted">
                            {item.tier != null ? t("tier", { tier: item.tier }) : item.slug}
                          </div>
                        </div>
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
        </>
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
