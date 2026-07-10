"use client";

import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AiUsageTile } from "./AiUsageTile";
import { type DashboardData, dashboardApi } from "./api";
import { CatalogCountsTile } from "./CatalogCountsTile";
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

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await dashboardApi.request<DashboardData>("/admin/dashboard");
      setData(payload);
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
    return <p className="text-sm text-[#6B5E4C]">{t("loading")}</p>;
  }

  if (error || !data) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-[#9B2C2C]">{error ?? t("error")}</p>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-[#E8DFD0] px-4 text-sm"
          onClick={() => void load()}
        >
          {t("retry")}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-[#6B5E4C]">
        {t("cachedAt", { at: new Date(data.cached_at).toLocaleString(locale) })}
      </p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <GmvTile gmvNgwee={data.gmv_ngwee} locale={locale} />
        <PayoutLiabilitiesTile liabilities={data.payout_liabilities} locale={locale} />
        <ReconciliationTile reconciliation={data.reconciliation} locale={locale} />
        <OrdersStatusTile ordersByStatus={data.orders_by_status} />
        <CatalogCountsTile counts={data.counts} />
        <AiUsageTile aiUsage={data.ai_usage} />
        <FunnelTile funnel={data.funnel} className="sm:col-span-2 xl:col-span-3" />
      </div>
      <p className="font-mono text-xs text-[#6B5E4C]">
        {t("liabilitiesTotal", {
          amount: formatK(data.payout_liabilities.total_ngwee, { locale }),
        })}
      </p>
    </div>
  );
}
