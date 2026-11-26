"use client";

import { formatK } from "@vergeo/i18n";
import { LcBanknote } from "@vergeo/ui/src/lucide-icons";
import { StatCard } from "@vergeo/ui/src/stat-card";
import { useTranslations } from "next-intl";

type GmvTileProps = {
  gmvNgwee: number;
  locale: string;
};

export function GmvTile({ gmvNgwee, locale }: GmvTileProps) {
  const t = useTranslations("admin.dashboard.gmv");
  const isEmpty = gmvNgwee === 0;

  return (
    <div className="space-y-1">
      <StatCard
        label={t("title")}
        value={formatK(gmvNgwee, { locale })}
        icon={<LcBanknote className="size-5" duotone aria-hidden />}
        iconHue="green"
        data-testid="dashboard-gmv"
      />
      {isEmpty ? (
        <p className="text-xs text-text-2" data-testid="gmv-empty">
          {t("empty")}
        </p>
      ) : (
        <p className="text-xs text-text-2">{t("subtitle")}</p>
      )}
    </div>
  );
}
