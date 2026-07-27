"use client";

import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";

import { intakeApi, type IntakeQueueItem } from "./api";

type IntakeQueueProps = {
  locale: string;
};

export function IntakeQueue({ locale }: IntakeQueueProps) {
  const t = useTranslations("admin.intake.queue");
  const tRoot = useTranslations("admin.intake");
  const [items, setItems] = useState<IntakeQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      setItems(await intakeApi.request<IntakeQueueItem[]>("/admin/intake"));
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
    return <p className="text-sm text-muted">{tRoot("loading")}</p>;
  }

  if (error) {
    return (
      <AdminLoadFailure
        permissionDenied={permissionDenied}
        message={error}
        retryLabel={tRoot("error.retry")}
        onRetry={() => void load()}
      />
    );
  }

  if (items.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border p-4" data-testid="intake-empty">
        <p className="text-sm font-medium text-text">{tRoot("empty.title")}</p>
        <p className="text-xs text-muted">{tRoot("empty.body")}</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="intake-queue">
        <thead>
          <tr className="text-left text-xs uppercase text-muted">
            <th className="p-2">{t("vendor")}</th>
            <th className="p-2">{t("product")}</th>
            <th className="p-2">{t("price")}</th>
            <th className="p-2">{t("tier")}</th>
            <th className="p-2">{t("submitted")}</th>
            <th className="p-2" />
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.session_id} className="border-t border-border">
              <td className="p-2">{item.vendor_display_name ?? item.vendor_id}</td>
              <td className="p-2">{item.title ?? "—"}</td>
              <td className="p-2">{item.price_ngwee === null ? "—" : formatK(item.price_ngwee)}</td>
              <td className="p-2">{item.vendor_kyc_tier ?? "—"}</td>
              <td className="p-2">{item.submitted_at ?? "—"}</td>
              <td className="p-2">
                <Link
                  href={`/${locale}/intake/${item.session_id}`}
                  className="inline-flex min-h-11 items-center rounded-md border border-border px-3"
                >
                  {t("open")}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
