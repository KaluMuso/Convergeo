import { describe, expect, it } from "vitest";

import { buildLogisticsPills } from "./logistics-pills";

import type { CatalogListing } from "./listing-grid";

const labels = {
  nearest: "{distance} away",
  belowMedian: "Below median",
  delivery: "Lusaka delivery",
  pickup: "Pickup available",
};

function makeListing(overrides: Partial<CatalogListing> = {}): CatalogListing {
  return {
    id: "listing-1",
    title: "Sample",
    productSlug: "sample",
    vendorName: "Vendor",
    priceNgwee: 10_000,
    condition: "new",
    inStock: true,
    imagePublicId: null,
    rating: 0,
    reviewCount: 0,
    distanceM: null,
    belowMedian: false,
    deliveryAvailable: false,
    pickupAvailable: false,
    ...overrides,
  };
}

describe("buildLogisticsPills", () => {
  it("returns no pills when no logistics signals are present", () => {
    expect(buildLogisticsPills(makeListing(), labels)).toEqual([]);
  });

  it("maps distance to a nearest pill", () => {
    const pills = buildLogisticsPills(makeListing({ distanceM: 2300 }), labels);
    expect(pills).toEqual([expect.objectContaining({ key: "nearest", label: "2.3 km away" })]);
  });

  it("maps below_median and fulfillment flags to pills", () => {
    const pills = buildLogisticsPills(
      makeListing({
        belowMedian: true,
        deliveryAvailable: true,
        pickupAvailable: true,
      }),
      labels,
    );
    expect(pills.map((pill) => pill.key)).toEqual(["below-median", "delivery", "pickup"]);
  });
});
