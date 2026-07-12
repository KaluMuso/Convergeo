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
          <dt className="text-muted">{t("vendors")}</dt>
          <dd className="font-mono font-medium text-text">{counts.vendors}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="text-muted">{t("listings")}</dt>
          <dd className="font-mono font-medium text-text">{counts.listings}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="text-muted">{t("products")}</dt>
          <dd className="font-mono font-medium text-text">{counts.products}</dd>
        </div>
      </dl>
    </TileShell>
  );
}
