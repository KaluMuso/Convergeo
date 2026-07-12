"use client";

import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";

import { type PayoutLiabilities } from "./api";
import { TileShell } from "./TileShell";

type PayoutLiabilitiesTileProps = {
  liabilities: PayoutLiabilities;
  locale: string;
};

export function PayoutLiabilitiesTile({ liabilities, locale }: PayoutLiabilitiesTileProps) {
  const t = useTranslations("admin.dashboard.payoutLiabilities");

  return (
    <TileShell title={t("title")} subtitle={t("subtitle")}>
      <dl className="space-y-2 text-sm">
        <div className="flex items-center justify-between gap-2">
          <dt className="text-muted">{t("escrowHeld")}</dt>
          <dd className="font-mono font-medium text-text">
            {formatK(liabilities.escrow_held_ngwee, { locale })}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="text-muted">{t("releasedUnpaid")}</dt>
          <dd className="font-mono font-medium text-text">
            {formatK(liabilities.released_unpaid_ngwee, { locale })}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-2 border-t border-border pt-2">
          <dt className="font-medium text-text">{t("total")}</dt>
          <dd className="font-mono text-lg font-semibold text-text">
            {formatK(liabilities.total_ngwee, { locale })}
          </dd>
        </div>
      </dl>
    </TileShell>
  );
}
