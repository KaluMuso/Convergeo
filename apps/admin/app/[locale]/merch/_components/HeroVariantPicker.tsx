"use client";

import { useTranslations } from "next-intl";

const VARIANT_STYLES: Record<string, { bg: string; accent: string }> = {
  "editorial-light": { bg: "bg-bg", accent: "border-primary" },
  "gradient-dark": {
    bg: "bg-gradient-to-br from-primary-deep to-primary",
    accent: "border-border",
  },
  carousel: { bg: "bg-bg-2", accent: "border-danger" },
  default: { bg: "bg-bg-2", accent: "border-muted" },
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
        <h3 className="text-sm font-semibold text-text">{t("title")}</h3>
        <p className="text-xs text-muted">{t("subtitle")}</p>
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
                isSelected ? style.accent : "border-transparent hover:border-border",
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
                  variant.variant_key === "gradient-dark" ? "text-white" : "text-text",
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
