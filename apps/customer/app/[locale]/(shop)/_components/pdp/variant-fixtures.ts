/** Shared PDP variant fixtures (not a test file). */
import type { ListingVariantOption, VariantOptionGroup } from "./variant-selection";

export const GROUPS: VariantOptionGroup[] = [
  {
    id: "g-colour",
    name: "Colour",
    display: "swatch",
    values: [
      { id: "red", label: "Red", swatchHex: "#C0392B" },
      { id: "blue", label: "Blue", swatchHex: "#2E86C1" },
    ],
  },
  {
    id: "g-size",
    name: "Size",
    display: "pill",
    values: [
      { id: "s", label: "S", swatchHex: null },
      { id: "m", label: "M", swatchHex: null },
      { id: "l", label: "L", swatchHex: null },
    ],
  },
];

export function variant(id: string, ids: string[], overrides: Partial<ListingVariantOption> = {}) {
  return {
    id,
    sku: id.toUpperCase(),
    optionValueIds: ids,
    priceNgwee: 20_000,
    compareAtNgwee: null,
    stockQty: 3,
    inStock: true,
    imagePublicId: null,
    ...overrides,
  } satisfies ListingVariantOption;
}

/** Red: S, M (M sold out). Blue: M, L. Nothing offers Red/L or Blue/S. */
export const VARIANTS: ListingVariantOption[] = [
  variant("red-s", ["red", "s"]),
  variant("red-m", ["red", "m"], { stockQty: 0, inStock: false }),
  variant("blue-m", ["blue", "m"], { priceNgwee: 25_000, imagePublicId: "img/blue" }),
  variant("blue-l", ["blue", "l"]),
];
