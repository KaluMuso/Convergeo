"use client";

import { useTranslations } from "next-intl";

import { type AiUsageTile as AiUsageData } from "./api";
import { TileShell } from "./TileShell";

type AiUsageTileProps = {
  aiUsage: AiUsageData;
};

export function AiUsageTile({ aiUsage }: AiUsageTileProps) {
  const t = useTranslations("admin.dashboard.aiUsage");
  const status = aiUsage.killed ? "danger" : aiUsage.flagged ? "warning" : undefined;

  return (
    <TileShell title={t("title")} subtitle={t("subtitle")} status={status}>
      {aiUsage.killed ? (
        <p className="text-sm font-medium text-danger" data-testid="ai-killed">
          {t("killed")}
        </p>
      ) : null}
      {aiUsage.data_available ? (
        <p className="text-sm text-text">
          {t("spendVsCap", {
            spend: aiUsage.spend_usd ?? 0,
            cap: aiUsage.cap_usd,
          })}
        </p>
      ) : (
        <div className="space-y-2">
          <p className="inline-flex min-h-8 items-center rounded-full bg-warning/10 px-3 text-sm font-medium text-warning">
            {t("noData")}
          </p>
          <p className="text-xs text-muted">{t("noDataHint", { cap: aiUsage.cap_usd })}</p>
        </div>
      )}
    </TileShell>
  );
}
