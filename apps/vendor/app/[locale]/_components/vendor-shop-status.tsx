"use client";

import { StatusChip } from "@vergeo/ui/src/status-chip";
import { useTranslations } from "next-intl";

type VendorShopStatusCardProps = {
  shopLive: boolean;
  idVerified: boolean;
  payoutSet: boolean | null;
};

export function VendorShopStatusCard({
  shopLive,
  idVerified,
  payoutSet,
}: VendorShopStatusCardProps) {
  const t = useTranslations("vendor");
  return (
    <section
      className="rounded-xl border border-border bg-surface p-4 shadow-1"
      data-testid="vendor-shop-status"
      aria-labelledby="vendor-shop-status-heading"
    >
      <h2 id="vendor-shop-status-heading" className="font-display text-h4 text-display-ink">
        {t("home.shopStatus.heading")}
      </h2>
      <ul className="mt-3 flex flex-col gap-2">
        <li className="flex items-center justify-between gap-2 text-sm">
          <span className="text-text-2">{t("home.shopStatus.shopLive")}</span>
          <StatusChip
            tone={shopLive ? "success" : "warning"}
            label={shopLive ? t("home.shopStatus.yes") : t("home.shopStatus.notYet")}
          />
        </li>
        <li className="flex items-center justify-between gap-2 text-sm">
          <span className="text-text-2">{t("home.shopStatus.idVerified")}</span>
          <StatusChip
            tone={idVerified ? "success" : "warning"}
            label={idVerified ? t("home.shopStatus.yes") : t("home.shopStatus.notYet")}
          />
        </li>
        <li className="flex items-center justify-between gap-2 text-sm">
          <span className="text-text-2">{t("home.shopStatus.payoutSet")}</span>
          {payoutSet === null ? (
            <span className="text-xs text-text-3">—</span>
          ) : (
            <StatusChip
              tone={payoutSet ? "success" : "warning"}
              label={payoutSet ? t("home.shopStatus.yes") : t("home.shopStatus.notYet")}
            />
          )}
        </li>
      </ul>
    </section>
  );
}
