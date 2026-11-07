"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { type ReconciliationTile as ReconciliationData } from "./api";
import { reconciliationDisplayStatus } from "./dashboard-truth";
import { TileShell } from "./TileShell";

type ReconciliationTileProps = {
  reconciliation: ReconciliationData;
  locale: string;
};

export function ReconciliationTile({ reconciliation, locale }: ReconciliationTileProps) {
  const t = useTranslations("admin.dashboard.reconciliation");
  const [expanded, setExpanded] = useState(false);
  const display = reconciliationDisplayStatus(reconciliation);
  const shellStatus = display === "red" ? "danger" : display === "green" ? "success" : "warning";

  return (
    <TileShell title={t("title")} subtitle={t("subtitle")} status={shellStatus}>
      <div className="space-y-3">
        <p
          className={
            display === "red"
              ? "inline-flex min-h-8 items-center rounded-full bg-danger/10 px-3 text-sm font-medium text-danger"
              : display === "green"
                ? "inline-flex min-h-8 items-center rounded-full bg-success/10 px-3 text-sm font-medium text-success"
                : "inline-flex min-h-8 items-center rounded-full bg-warning/10 px-3 text-sm font-medium text-warning"
          }
          data-testid="reconciliation-status"
          data-status={display}
        >
          {display === "red"
            ? t("statusRed")
            : display === "green"
              ? t("statusGreen")
              : t("statusUnknown")}
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
        {display === "unknown" ? (
          <p className="text-xs text-muted">{t("noReportDependency")}</p>
        ) : null}
        {reconciliation.evidence_state ? (
          <p className="text-xs text-muted">
            {t("evidenceState", { state: t(`states.${reconciliation.evidence_state}`) })}
          </p>
        ) : null}
        {reconciliation.provenance ? (
          <p className="text-xs text-muted">
            {t(
              reconciliation.provenance === "VERSIONED_ACCOUNT_BOUND"
                ? "provenanceBound"
                : "provenanceLegacy",
            )}
          </p>
        ) : null}
        {reconciliation.version_number ? (
          <p className="text-xs text-muted">
            {t("version", { number: reconciliation.version_number })}
          </p>
        ) : null}
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
            {display === "red" ? (
              <p className="mt-2 text-danger">{t("mismatchAlert")}</p>
            ) : display === "green" ? (
              <p className="mt-2 text-success">{t("cleanDay")}</p>
            ) : (
              <p className="mt-2 text-warning">{t("noReportDependency")}</p>
            )}
            {reconciliation.provider_account_id ? (
              <p className="mt-2 text-xs">
                {t("accountCurrency", {
                  account: reconciliation.provider_account_id,
                  currency: reconciliation.currency ?? "",
                })}
              </p>
            ) : null}
            {reconciliation.discrepancies ? (
              <pre className="mt-2 whitespace-pre-wrap break-words text-xs">
                {JSON.stringify(reconciliation.discrepancies, null, 2)}
              </pre>
            ) : null}
          </div>
        ) : null}
      </div>
    </TileShell>
  );
}
