"use client";

import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { classifyAdminRequestError } from "./admin-request";
import { AiUsageTile } from "./AiUsageTile";
import { type DashboardData, dashboardApi } from "./api";
import { CatalogCountsTile } from "./CatalogCountsTile";
import { isAnalyticsTrafficEmpty } from "./dashboard-truth";
import { FunnelTile } from "./FunnelTile";
import { GmvTile } from "./GmvTile";
import { OrdersStatusTile } from "./OrdersStatusTile";
import { PayoutLiabilitiesTile } from "./PayoutLiabilitiesTile";
import { ReconciliationTile } from "./ReconciliationTile";

type DashboardBoardProps = {
  locale: string;
};

export function DashboardBoard({ locale }: DashboardBoardProps) {
  const t = useTranslations("admin.dashboard");
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      const payload = await dashboardApi.request<DashboardData>("/admin/dashboard");
      setData(payload);
    } catch (err) {
      const classified = classifyAdminRequestError(err);
      if (classified.kind === "permission") {
        setPermissionDenied(true);
        setError(t("permissionDenied"));
      } else {
        setError(t("error"));
      }
      setData(null);
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

  if (permissionDenied) {
    return (
      <div className="space-y-2 rounded-md border border-warning/40 bg-warning/5 p-4">
        <p className="text-sm font-medium text-warning">{t("permissionDenied")}</p>
        <p className="text-xs text-muted">{t("permissionDeniedHint")}</p>
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

  if (error || !data) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-danger">{error ?? t("error")}</p>
        <p className="text-xs text-muted">{t("errorHint")}</p>
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

  const trafficEmpty = isAnalyticsTrafficEmpty(data);

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted">
        {t("cachedAt", { at: new Date(data.cached_at).toLocaleString(locale) })}
      </p>
      {trafficEmpty ? (
        <div
          className="space-y-1 rounded-md border border-border bg-bg p-3"
          data-testid="dashboard-empty-truth"
        >
          <p className="text-sm font-medium text-text">{t("emptyTrafficTitle")}</p>
          <p className="text-xs text-muted">{t("emptyTrafficBody")}</p>
          <p className="text-xs text-muted">{t("emptyTrafficDependency")}</p>
        </div>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <GmvTile gmvNgwee={data.gmv_ngwee} locale={locale} />
        <PayoutLiabilitiesTile liabilities={data.payout_liabilities} locale={locale} />
        <ReconciliationTile reconciliation={data.reconciliation} locale={locale} />
        <OrdersStatusTile ordersByStatus={data.orders_by_status} />
        <CatalogCountsTile counts={data.counts} />
        <AiUsageTile aiUsage={data.ai_usage} />
        <FunnelTile funnel={data.funnel} className="sm:col-span-2 xl:col-span-3" />
      </div>
      <p className="font-mono text-xs text-muted">
        {t("liabilitiesTotal", {
          amount: formatK(data.payout_liabilities.total_ngwee, { locale }),
        })}
      </p>
    </div>
  );
}
