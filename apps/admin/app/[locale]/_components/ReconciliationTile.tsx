"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { type ReconciliationTile as ReconciliationData } from "./api";
import { TileShell } from "./TileShell";

type ReconciliationTileProps = {
  reconciliation: ReconciliationData;
  locale: string;
};

export function ReconciliationTile({ reconciliation, locale }: ReconciliationTileProps) {
  const t = useTranslations("admin.dashboard.reconciliation");
  const [expanded, setExpanded] = useState(false);
  const isRed = reconciliation.status === "red" || reconciliation.has_mismatch;

  return (
    <TileShell title={t("title")} subtitle={t("subtitle")} status={isRed ? "danger" : "success"}>
      <div className="space-y-3">
        <p
          className={
            isRed
              ? "inline-flex min-h-8 items-center rounded-full bg-[#FDE8E8] px-3 text-sm font-medium text-[#9B2C2C]"
              : "inline-flex min-h-8 items-center rounded-full bg-[#E6F4EA] px-3 text-sm font-medium text-[#1E6B3A]"
          }
        >
          {isRed ? t("statusRed") : t("statusGreen")}
        </p>
        {reconciliation.report_date ? (
          <p className="text-sm text-[#6B5E4C]">
            {t("reportDate", {
              date: new Date(reconciliation.report_date).toLocaleDateString(locale),
            })}
          </p>
        ) : (
          <p className="text-sm text-[#6B5E4C]">{t("noReport")}</p>
        )}
        {reconciliation.report_id ? (
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-[#E8DFD0] px-3 text-sm font-medium text-[#2D4A7A]"
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? t("hideDrillIn") : t("drillIn")}
          </button>
        ) : null}
        {expanded && reconciliation.report_id ? (
          <div className="rounded-md border border-[#F0E9DE] bg-[#FAF7F2] p-3 text-sm">
            <p className="font-mono text-xs text-[#6B5E4C]">{reconciliation.report_id}</p>
            {isRed ? (
              <p className="mt-2 text-[#9B2C2C]">{t("mismatchAlert")}</p>
            ) : (
              <p className="mt-2 text-[#1E6B3A]">{t("cleanDay")}</p>
            )}
          </div>
        ) : null}
      </div>
    </TileShell>
  );
}
