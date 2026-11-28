import floorsDocument from "./listing-category-price-floors.json";

export type ListingCategoryPriceFloor = {
  pathPrefix: string;
  floorNgwee: number;
  label: string;
};

export const LISTING_CATEGORY_PRICE_FLOORS: readonly ListingCategoryPriceFloor[] =
  floorsDocument.categoryPathPrefixes;

/** Review flag key returned by the API when price is under the category floor (never blocks publish). */
export const LISTING_REVIEW_FLAG_PRICE_BELOW_CATEGORY_FLOOR = "price_below_category_floor" as const;

export function resolveListingCategoryFloorNgwee(
  categoryPath: string | null | undefined,
): { floorNgwee: number; pathPrefix: string } | null {
  const path = (categoryPath ?? "").trim();
  if (!path) {
    return null;
  }
  for (const entry of LISTING_CATEGORY_PRICE_FLOORS) {
    const prefix = entry.pathPrefix;
    if (path === prefix || path.startsWith(`${prefix}/`)) {
      return { floorNgwee: entry.floorNgwee, pathPrefix: prefix };
    }
  }
  return null;
}

export function isListingPriceBelowCategoryFloor(
  priceNgwee: number | null | undefined,
  categoryPath: string | null | undefined,
): boolean {
  if (typeof priceNgwee !== "number" || priceNgwee < 0) {
    return false;
  }
  const floor = resolveListingCategoryFloorNgwee(categoryPath);
  return floor !== null && priceNgwee < floor.floorNgwee;
}
