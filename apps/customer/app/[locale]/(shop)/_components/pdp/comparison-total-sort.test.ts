import { describe, expect, it } from "vitest";

import { comparisonTotalNgwee, sortComparisonListings, type ComparisonListing } from "./comparison";

const base = (id: string, price: number, fee: number | null): ComparisonListing => ({
  id,
  priceNgwee: price,
  condition: "new",
  vendor: {
    id: `v-${id}`,
    slug: id,
    displayName: id,
    preferredBadge: false,
    ratingAvg: null,
    ratingCount: 0,
    lat: null,
    lng: null,
    landmark: null,
  },
  deliveryAvailable: fee !== null,
  pickupAvailable: false,
  deliveryFeeNgwee: fee,
});

describe("comparisonTotalNgwee", () => {
  it("sorts lowest total with null fees last", () => {
    const listings = [
      { ...base("cheap", 100_000, null), deliveryAvailable: true },
      base("best", 120_000, 5_000),
      base("mid", 90_000, 20_000),
    ];
    const sorted = sortComparisonListings(listings, "total", {
      lat: -15.4167,
      lng: 28.2833,
    });
    expect(sorted.map((row) => row.id)).toEqual(["mid", "best", "cheap"]);
    expect(comparisonTotalNgwee({ ...base("x", 1, null), deliveryAvailable: true })).toBeNull();
  });
});
