"use client";

import { formatK } from "@vergeo/i18n";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";

import {
  lowestVariantPriceForValue,
  type ListingVariantOption,
  type VariantOptionGroup,
  type VariantOptionValue,
} from "./variant-swatches-math";

export type VariantSwatchesProps = {
  group: VariantOptionGroup;
  variants: ListingVariantOption[];
  selectedValueId?: string;
  cloudName?: string;
  fromPriceLabel: string;
  onSelect: (valueId: string) => void;
};

/**
 * Amazon-style image swatches for the visual option group (e.g. colour).
 * Wiring lives next to the gallery once buy-box props can pass variant state.
 */
export function VariantSwatches({
  group,
  variants,
  selectedValueId,
  cloudName,
  fromPriceLabel,
  onSelect,
}: VariantSwatchesProps) {
  if (group.display !== "swatch") {
    return null;
  }

  return (
    <div
      data-testid="pdp-variant-swatches"
      className="motion-safe flex flex-wrap gap-2"
    >
      {group.values.map((value: VariantOptionValue) => {
        const fromNgwee = lowestVariantPriceForValue(variants, value.id);
        const imageId =
          variants.find((variant) => variant.optionValueIds.includes(value.id))?.imagePublicId ??
          null;
        const selected = value.id === selectedValueId;
        return (
          <button
            key={value.id}
            type="button"
            aria-pressed={selected}
            onClick={() => onSelect(value.id)}
            className={[
              "flex w-24 flex-col gap-1 rounded border bg-surface p-1 text-left focus-visible:outline-none focus-visible:shadow-focusRing",
              selected ? "border-2 border-primary" : "border-border",
            ].join(" ")}
          >
            {imageId ? (
              <CloudinaryImage
                publicId={imageId}
                alt={value.label}
                width={128}
                ratio="1/1"
                cloudName={cloudName}
                className="h-20 w-full object-contain"
              />
            ) : (
              <span
                className="flex h-20 w-full items-center justify-center rounded text-xs"
                style={{ backgroundColor: value.swatchHex ?? "var(--bg-2)" }}
              >
                {value.label}
              </span>
            )}
            <span className="text-[11px] text-text-2">
              {fromNgwee !== null
                ? fromPriceLabel.replace("{price}", formatK(fromNgwee))
                : value.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
