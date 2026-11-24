import { describe, expect, it } from "vitest";

import { buildComparisonValueRow } from "./comparison-enrichment";
import type { ComparisonListing } from "./comparison";
import type { ProductListing } from "./pdp-interactive-body";

const baseProduct: ProductListing = {
  id: "l1",
  title: "Phone",
  priceNgwee: 50_000,
  condition: "new",
  productClass: "A",
  stockMode: "tracked",
  stockQty: 5,
  moq: 1,
  inStock: true,
  leadTimeDays: null,
  vendorCapacityPerWeek: null,
  fulfilmentMode: "stocked",
  vendor: {
    slug: "shop",
    displayName: "Shop",
    preferredBadge: false,
    ratingAvg: null,
    ratingCount: 0,
    landmark: null,
  },
  images: [],
};

const baseComparison: ComparisonListing = {
  id: "l1",
  priceNgwee: 50_000,
  condition: "new",
  vendor: {
    id: "v1",
    slug: "shop",
    displayName: "Shop",
    preferredBadge: false,
    ratingAvg: null,
    ratingCount: 0,
    lat: -15.4,
    lng: 28.3,
    landmark: null,
  },
  deliveryAvailable: true,
  pickupAvailable: true,
};

const labels = {
  buyBox: {
    inStockLabel: "In stock",
    outOfStockLabel: "Out",
    alwaysAvailableLabel: "Available",
    lowStockLabel: (n: number) => `Only ${n} left`,
  },
  delivery: {
    deliveryToday: "Today",
    deliveryTomorrow: "Tomorrow",
    deliveryDays: "{min}-{max} days",
    pickupToday: "Pickup today",
    pickupTomorrow: "Pickup tomorrow",
    pickupDays: "{min}-{max} days pickup",
  },
  madeToOrderDays: (days: number) => `Made ${days}d`,
};

describe("buildComparisonValueRow", () => {
  it("includes COD chip at K500 boundary only", () => {
    const atCap = buildComparisonValueRow(
      baseProduct,
      { ...baseComparison, priceNgwee: 50_000 },
      labels,
      { codCapNgwee: 50_000, codChipsEnabled: true },
    );
    const overCap = buildComparisonValueRow(
      baseProduct,
      { ...baseComparison, priceNgwee: 50_001 },
      labels,
      { codCapNgwee: 50_000, codChipsEnabled: true },
    );
    expect(atCap.chips).toContain("cod");
    expect(overCap.chips).not.toContain("cod");
  });
});
