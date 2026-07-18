"use client";

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

  return (
    <TileShell title={t("title")} subtitle={t("subtitle")} className={className}>
      {empty ? (
        <p className="mb-3 text-xs text-muted" data-testid="funnel-empty">
          {t("empty")}
        </p>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {steps.map((step) => (
          <div key={step.key} className="rounded-md border border-border bg-bg p-3">
            <p className="text-xs text-muted">{t(`steps.${step.key}`)}</p>
            <p className="mt-1 font-mono text-xl font-semibold text-text">{step.value}</p>
          </div>
        ))}
      </div>
    </TileShell>
  );
}
