"use client";

import { useTranslations } from "next-intl";

import { formatBytes } from "./size";

/**
 * M17-P04 — the D-V5 byte-honesty chip.
 *
 * Shown **before** any cellular play, never after. Telling someone a clip costs
 * about 2 MB after they have already spent it is not honesty, it is a receipt.
 */
export function SizeChip({ bytes }: { bytes: number | null | undefined }) {
  const t = useTranslations("clips");
  const size = formatBytes(bytes);

  if (!size) {
    return (
      <span
        data-testid="clip-size-chip"
        className="rounded-full bg-surface/80 px-2 py-1 text-xs text-muted"
      >
        {t("size.unknown")}
      </span>
    );
  }

  const formatted =
    size.unit === "MB"
      ? t("size.megabytes", { value: size.value })
      : t("size.kilobytes", { value: size.value });

  return (
    <span
      data-testid="clip-size-chip"
      aria-label={t("a11y.sizeChipLabel")}
      title={t("size.label", { size: formatted })}
      className="rounded-full bg-surface/80 px-2 py-1 text-xs font-medium text-text"
    >
      {t("size.chip", { size: formatted })}
    </span>
  );
}
