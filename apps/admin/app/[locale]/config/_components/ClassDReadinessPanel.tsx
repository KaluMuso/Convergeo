"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { configApi, type ClassDReadiness } from "./api";

export function ClassDReadinessPanel() {
  const t = useTranslations("admin.config");
  const locale = useLocale();
  const [data, setData] = useState<ClassDReadiness | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await configApi.request<ClassDReadiness>("/admin/config/class-d-readiness");
      setData(payload);
    } catch {
      setError(t("common.error"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return <p className="text-sm text-muted">{t("common.loading")}</p>;
  }

  if (error || !data) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-danger">{error ?? t("common.error")}</p>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
          onClick={() => void load()}
        >
          {t("common.retry")}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="admin-class-d-readiness">
      <p className="text-sm text-muted">{t("classD.help")}</p>
      <dl className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-md border border-border p-3">
          <dt className="text-xs uppercase tracking-wide text-muted">{t("classD.opsApproved")}</dt>
          <dd className="mt-1 font-medium text-text">
            {data.operations_approved ? t("common.enabled") : t("common.disabled")}
          </dd>
        </div>
        <div className="rounded-md border border-border p-3">
          <dt className="text-xs uppercase tracking-wide text-muted">
            {t("classD.customerRelease")}
          </dt>
          <dd className="mt-1 font-medium text-text">
            {data.customer_release ? t("common.enabled") : t("common.disabled")}
          </dd>
        </div>
        <div className="rounded-md border border-border p-3">
          <dt className="text-xs uppercase tracking-wide text-muted">{t("classD.escrowHours")}</dt>
          <dd className="mt-1 font-mono text-text">{data.escrow_hours}</dd>
        </div>
        <div className="rounded-md border border-border p-3">
          <dt className="text-xs uppercase tracking-wide text-muted">
            {t("classD.shopperVisible")}
          </dt>
          <dd className="mt-1 font-medium text-text">
            {data.shopper_visible ? t("classD.visible") : t("classD.hidden")}
          </dd>
        </div>
      </dl>
      <p className="text-sm text-text" role="note">
        {t("classD.flagNote")}
      </p>
      <Link
        href={`/${locale}/config/flags`}
        className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline-offset-2 hover:underline"
      >
        {t("classD.openFlags")}
      </Link>
    </div>
  );
}
