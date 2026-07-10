"use client";

import { useTranslations } from "next-intl";

import { type AiUsageTile as AiUsageData } from "./api";
import { TileShell } from "./TileShell";

type AiUsageTileProps = {
  aiUsage: AiUsageData;
};

export function AiUsageTile({ aiUsage }: AiUsageTileProps) {
  const t = useTranslations("admin.dashboard.aiUsage");

  return (
    <TileShell
      title={t("title")}
      subtitle={t("subtitle")}
      status={aiUsage.flagged ? "warning" : undefined}
    >
      {aiUsage.data_available ? (
        <p className="text-sm text-[#2A2118]">
          {t("spendVsCap", {
            spend: aiUsage.spend_usd ?? 0,
            cap: aiUsage.cap_usd,
          })}
        </p>
      ) : (
        <div className="space-y-2">
          <p className="inline-flex min-h-8 items-center rounded-full bg-[#FFF4E5] px-3 text-sm font-medium text-[#8A5A00]">
            {t("noData")}
          </p>
          <p className="text-xs text-[#6B5E4C]">{t("noDataHint", { cap: aiUsage.cap_usd })}</p>
        </div>
      )}
    </TileShell>
  );
}
