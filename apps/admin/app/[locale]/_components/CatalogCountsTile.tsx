"use client";

import { useTranslations } from "next-intl";

import { type CatalogCounts } from "./api";
import { TileShell } from "./TileShell";

type CatalogCountsTileProps = {
  counts: CatalogCounts;
};

export function CatalogCountsTile({ counts }: CatalogCountsTileProps) {
  const t = useTranslations("admin.dashboard.counts");

  return (
    <TileShell title={t("title")} subtitle={t("subtitle")}>
      <dl className="space-y-2 text-sm">
        <div className="flex items-center justify-between gap-2">
          <dt className="text-[#6B5E4C]">{t("vendors")}</dt>
          <dd className="font-mono font-medium text-[#2A2118]">{counts.vendors}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="text-[#6B5E4C]">{t("listings")}</dt>
          <dd className="font-mono font-medium text-[#2A2118]">{counts.listings}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="text-[#6B5E4C]">{t("products")}</dt>
          <dd className="font-mono font-medium text-[#2A2118]">{counts.products}</dd>
        </div>
      </dl>
    </TileShell>
  );
}
