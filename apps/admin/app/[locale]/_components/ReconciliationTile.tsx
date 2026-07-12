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
              ? "inline-flex min-h-8 items-center rounded-full bg-danger/10 px-3 text-sm font-medium text-danger"
              : "inline-flex min-h-8 items-center rounded-full bg-success/10 px-3 text-sm font-medium text-success"
          }
        >
          {isRed ? t("statusRed") : t("statusGreen")}
        </p>
        {reconciliation.report_date ? (
          <p className="text-sm text-muted">
            {t("reportDate", {
              date: new Date(reconciliation.report_date).toLocaleDateString(locale),
            })}
          </p>
        ) : (
          <p className="text-sm text-muted">{t("noReport")}</p>
        )}
        {reconciliation.report_id ? (
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-sm font-medium text-primary"
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? t("hideDrillIn") : t("drillIn")}
          </button>
        ) : null}
        {expanded && reconciliation.report_id ? (
          <div className="rounded-md border border-border bg-bg p-3 text-sm">
            <p className="font-mono text-xs text-muted">{reconciliation.report_id}</p>
            {isRed ? (
              <p className="mt-2 text-danger">{t("mismatchAlert")}</p>
            ) : (
              <p className="mt-2 text-success">{t("cleanDay")}</p>
            )}
          </div>
        ) : null}
      </div>
    </TileShell>
  );
}
