"use client";

import { resolveHeroVariant } from "@vergeo/ui/src/merch/hero-registry";
import { useTranslations } from "next-intl";

const VARIANT_STYLES: Record<string, { bg: string; accent: string; label: string }> = {
  "editorial-light": { bg: "bg-bg", accent: "border-primary", label: "text-text" },
  "gradient-dark": {
    bg: "bg-gradient-to-br from-primary-deep to-primary",
    accent: "border-primary-tint",
    label: "text-[var(--primary-btn-fg)]",
  },
  carousel: { bg: "bg-bg-2", accent: "border-danger", label: "text-text" },
  default: { bg: "bg-surface", accent: "border-border", label: "text-text" },
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
          const Preview = resolveHeroVariant(variant.variant_key);
          return (
            <button
              key={variant.variant_key}
              type="button"
              aria-pressed={isSelected}
              onClick={() => onSelect(variant.variant_key)}
              className={[
                "flex min-h-32 flex-col gap-2 overflow-hidden rounded-lg border-2 p-2 text-left transition",
                style.bg,
                style.label,
                isSelected ? style.accent : "border-transparent hover:border-border",
              ].join(" ")}
            >
              <div className="pointer-events-none origin-top-left scale-[0.35] overflow-hidden rounded-md border border-border/50 bg-bg">
                <div className="w-[280px]">
                  <Preview
                    eyebrow={t("previewEyebrow")}
                    title={t("previewTitle")}
                    subtitle={t("previewSubtitle")}
                    primaryCta={
                      <span className="rounded-pill bg-primary px-2 py-0.5 text-xs">
                        {t("previewCta")}
                      </span>
                    }
                  />
                </div>
              </div>
              <span className="text-xs font-medium">{variant.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
