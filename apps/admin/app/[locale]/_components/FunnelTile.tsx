"use client";

import { Meter } from "@vergeo/ui/src/meter";
import { useTranslations } from "next-intl";

import { type FunnelSnapshot } from "./api";
import { isFunnelEmpty } from "./dashboard-truth";
import { TileShell } from "./TileShell";

type FunnelTileProps = {
  funnel: FunnelSnapshot;
  className?: string;
};

export function FunnelTile({ funnel, className }: FunnelTileProps) {
  const t = useTranslations("admin.dashboard.funnel");
  const empty = isFunnelEmpty(funnel);

  const steps = [
    { key: "checkout_started", value: funnel.checkout_started },
    { key: "checkout_completed", value: funnel.checkout_completed },
    { key: "orders_placed", value: funnel.orders_placed },
    { key: "orders_completed", value: funnel.orders_completed },
  ] as const;

  // Share of the top of funnel (checkout_started) — the classic funnel descent.
  const base = funnel.checkout_started;

  return (
    <TileShell title={t("title")} subtitle={t("subtitle")} className={className}>
      {empty ? (
        <p className="mb-3 text-xs text-muted" data-testid="funnel-empty">
          {t("empty")}
        </p>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {steps.map((step) => {
          const pct = base > 0 ? Math.round((step.value / base) * 100) : 0;
          return (
            <div key={step.key} className="rounded-md border border-border bg-bg p-3">
              <p className="text-xs text-muted">{t(`steps.${step.key}`)}</p>
              <p className="mt-1 font-mono text-xl font-semibold text-text">{step.value}</p>
              <Meter value={pct} label={t("conversionAria", { pct })} className="mt-2" />
              <p className="mt-1 text-right text-xs text-muted">{t("conversion", { pct })}</p>
            </div>
          );
        })}
      </div>
    </TileShell>
  );
}
