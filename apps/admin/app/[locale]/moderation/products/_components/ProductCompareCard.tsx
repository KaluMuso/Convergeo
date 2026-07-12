"use client";

import { useTranslations } from "next-intl";

import type { ProductSummary } from "./api";

type ProductCompareCardProps = {
  product: ProductSummary;
  actionLabel: string;
  onSelectSurvivor: () => void;
};

export function ProductCompareCard({
  product,
  actionLabel,
  onSelectSurvivor,
}: ProductCompareCardProps) {
  const t = useTranslations("admin.moderation.queue");

  return (
    <div className="space-y-3 rounded-md border border-border bg-bg p-3">
      <div>
        <h2 className="font-medium text-text">{product.name}</h2>
        <p className="font-mono text-xs text-muted">{product.slug}</p>
      </div>
      <dl className="space-y-1 text-sm">
        <div className="flex justify-between gap-2">
          <dt className="text-muted">{t("status")}</dt>
          <dd className="text-text">{product.status}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-muted">{t("category")}</dt>
          <dd className="truncate font-mono text-xs text-text">{product.category_id}</dd>
        </div>
        <div>
          <dt className="text-muted">{t("aliases")}</dt>
          <dd className="mt-1 text-text">
            {product.aliases.length > 0 ? product.aliases.join(", ") : t("noAliases")}
          </dd>
        </div>
      </dl>
      <button
        type="button"
        className="inline-flex min-h-11 w-full items-center justify-center rounded-md border border-primary px-4 text-sm font-medium text-primary"
        onClick={onSelectSurvivor}
      >
        {actionLabel}
      </button>
    </div>
  );
}
