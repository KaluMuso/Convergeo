import { describe, expect, it } from "vitest";

import {
  isListingPriceBelowCategoryFloor,
  LISTING_CATEGORY_PRICE_FLOORS,
  resolveListingCategoryFloorNgwee,
} from "./listing-category-price-floors";

describe("listing-category-price-floors", () => {
  it("exposes the four electronics floors in ngwee", () => {
    expect(LISTING_CATEGORY_PRICE_FLOORS.map((row) => row.floorNgwee)).toEqual([
      30_000, 100_000, 20_000, 10_000,
    ]);
  });

  it("matches longest category path prefix", () => {
    expect(resolveListingCategoryFloorNgwee("electronics/mobile-phones")?.floorNgwee).toBe(30_000);
    expect(resolveListingCategoryFloorNgwee("electronics/mobile-phones/feature")?.floorNgwee).toBe(
      30_000,
    );
    expect(resolveListingCategoryFloorNgwee("electronics/cameras")).toEqual({
      floorNgwee: 20_000,
      pathPrefix: "electronics/cameras",
    });
  });

  it("flags prices below the floor without blocking semantics", () => {
    expect(isListingPriceBelowCategoryFloor(29_999, "electronics/mobile-phones")).toBe(true);
    expect(isListingPriceBelowCategoryFloor(30_000, "electronics/mobile-phones")).toBe(false);
    expect(isListingPriceBelowCategoryFloor(500, "home/kitchen")).toBe(false);
  });
});
