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
    <div className="space-y-3 rounded-md border border-[#F0E9DE] bg-[#FAF7F2] p-3">
      <div>
        <h2 className="font-medium text-[#2A2118]">{product.name}</h2>
        <p className="font-mono text-xs text-[#6B5E4C]">{product.slug}</p>
      </div>
      <dl className="space-y-1 text-sm">
        <div className="flex justify-between gap-2">
          <dt className="text-[#6B5E4C]">{t("status")}</dt>
          <dd className="text-[#2A2118]">{product.status}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-[#6B5E4C]">{t("category")}</dt>
          <dd className="truncate font-mono text-xs text-[#2A2118]">{product.category_id}</dd>
        </div>
        <div>
          <dt className="text-[#6B5E4C]">{t("aliases")}</dt>
          <dd className="mt-1 text-[#2A2118]">
            {product.aliases.length > 0 ? product.aliases.join(", ") : t("noAliases")}
          </dd>
        </div>
      </dl>
      <button
        type="button"
        className="inline-flex min-h-11 w-full items-center justify-center rounded-md border border-[#2D4A7A] px-4 text-sm font-medium text-[#2D4A7A]"
        onClick={onSelectSurvivor}
      >
        {actionLabel}
      </button>
    </div>
  );
}
