export type {
  ListingVariantOption,
  VariantOptionGroup,
  VariantOptionValue,
} from "./variant-selection";
import type { ListingVariantOption } from "./variant-selection";

export function lowestVariantPriceForValue(
  variants: ListingVariantOption[],
  valueId: string,
): number | null {
  const prices = variants
    .filter((variant) => variant.optionValueIds.includes(valueId))
    .map((variant) => variant.priceNgwee);
  if (prices.length === 0) {
    return null;
  }
  return Math.min(...prices);
}
