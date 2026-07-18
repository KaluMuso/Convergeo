"use client";

import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";

import { TileShell } from "./TileShell";

type GmvTileProps = {
  gmvNgwee: number;
  locale: string;
};

export function GmvTile({ gmvNgwee, locale }: GmvTileProps) {
  const t = useTranslations("admin.dashboard.gmv");
  const isEmpty = gmvNgwee === 0;

  return (
    <TileShell title={t("title")} subtitle={t("subtitle")}>
      <p className="font-mono text-2xl font-semibold text-text">{formatK(gmvNgwee, { locale })}</p>
      {isEmpty ? (
        <p className="mt-2 text-xs text-muted" data-testid="gmv-empty">
          {t("empty")}
        </p>
      ) : null}
    </TileShell>
  );
}
