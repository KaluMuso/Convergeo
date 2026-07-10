"use client";

import { useTranslations } from "next-intl";

const VARIANT_STYLES: Record<string, { bg: string; accent: string }> = {
  "editorial-light": { bg: "bg-[#FAF7F2]", accent: "border-[#2D4A7A]" },
  "gradient-dark": {
    bg: "bg-gradient-to-br from-[#1A2744] to-[#2D4A7A]",
    accent: "border-[#E8DFD0]",
  },
  carousel: { bg: "bg-[#F0E9DE]", accent: "border-[#C45C3E]" },
  default: { bg: "bg-[#E8DFD0]", accent: "border-[#6B5E4C]" },
};

type HeroVariantPickerProps = {
  variants: Array<{ variant_key: string; label: string }>;
  selected: string;
  onSelect: (variantKey: string) => void;
};

export function HeroVariantPicker({ variants, selected, onSelect }: HeroVariantPickerProps) {
  const t = useTranslations("admin.merch.hero");

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-[#2A2118]">{t("title")}</h3>
        <p className="text-xs text-[#6B5E4C]">{t("subtitle")}</p>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {variants.map((variant) => {
          const style = VARIANT_STYLES[variant.variant_key] ?? VARIANT_STYLES.default!;
          const isSelected = variant.variant_key === selected;
          return (
            <button
              key={variant.variant_key}
              type="button"
              aria-pressed={isSelected}
              onClick={() => onSelect(variant.variant_key)}
              className={[
                "flex min-h-24 flex-col gap-2 rounded-lg border-2 p-3 text-left transition",
                style.bg,
                isSelected ? style.accent : "border-transparent hover:border-[#C4B8A8]",
              ].join(" ")}
            >
              <span
                className={[
                  "h-10 w-full rounded",
                  variant.variant_key === "gradient-dark" ? "bg-white/20" : "bg-white/60",
                ].join(" ")}
              />
              <span
                className={[
                  "text-xs font-medium",
                  variant.variant_key === "gradient-dark" ? "text-white" : "text-[#2A2118]",
                ].join(" ")}
              >
                {variant.label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
