"use client";

import { useTranslations } from "next-intl";

import { type FunnelSnapshot } from "./api";
import { TileShell } from "./TileShell";

type FunnelTileProps = {
  funnel: FunnelSnapshot;
  className?: string;
};

export function FunnelTile({ funnel, className }: FunnelTileProps) {
  const t = useTranslations("admin.dashboard.funnel");

  const steps = [
    { key: "checkout_started", value: funnel.checkout_started },
    { key: "checkout_completed", value: funnel.checkout_completed },
    { key: "orders_placed", value: funnel.orders_placed },
    { key: "orders_completed", value: funnel.orders_completed },
  ] as const;

  return (
    <TileShell title={t("title")} subtitle={t("subtitle")} className={className}>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {steps.map((step) => (
          <div key={step.key} className="rounded-md border border-[#F0E9DE] bg-[#FAF7F2] p-3">
            <p className="text-xs text-[#6B5E4C]">{t(`steps.${step.key}`)}</p>
            <p className="mt-1 font-mono text-xl font-semibold text-[#2A2118]">{step.value}</p>
          </div>
        ))}
      </div>
    </TileShell>
  );
}
