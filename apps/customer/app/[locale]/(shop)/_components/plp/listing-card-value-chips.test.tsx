// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

import { ListingCard, type ListingCardLabels } from "./listing-card";

import type { CatalogListing } from "./listing-grid";

vi.mock("./use-local-wishlist", () => ({
  useLocalWishlist: () => ({
    isWishlisted: false,
    toggleWishlist: () => undefined,
    enabled: false,
  }),
}));

const baseLabels: ListingCardLabels = {
  vendor: "{vendor}",
  noReviews: "No reviews",
  reviewCount: "{count} reviews",
  quickAdd: "Add",
  wishlist: "Save",
  outOfStock: "Sold out",
  sellersFrom: "{count} sellers from {price}",
  deliversTodayPill: "Delivers today (Lusaka)",
  delivery: {
    deliveryToday: "Delivers today",
    deliveryTomorrow: "Tomorrow",
    deliveryDays: "In {min}–{max} days",
    pickupToday: "Pickup today",
    pickupTomorrow: "Pickup tomorrow",
    pickupDays: "Pickup in {min}–{max} days",
  },
};

const baseListing: CatalogListing = {
  id: "l1",
  title: "Phone",
  productSlug: "phone",
  vendorName: "Shop",
  priceNgwee: 100_000,
  condition: "new",
  inStock: true,
  imagePublicId: null,
  rating: 4,
  reviewCount: 1,
  distanceM: null,
  belowMedian: false,
  deliveryAvailable: true,
  pickupAvailable: false,
  fulfilmentMode: "stocked",
};

describe("ListingCard value chips", () => {
  it("skips seller line when productSellerCount is absent", () => {
    render(<ListingCard locale="en" listing={baseListing} labels={baseLabels} />);
    expect(screen.queryByTestId("listing-card-sellers-from")).not.toBeInTheDocument();
  });

  it("shows delivers-today pill when estimate is today", () => {
    const noon = new Date("2026-06-02T10:00:00Z");
    vi.useFakeTimers();
    vi.setSystemTime(noon);
    render(<ListingCard locale="en" listing={baseListing} labels={baseLabels} />);
    expect(screen.getAllByTestId("listing-card-delivers-today")).toHaveLength(1);
  });
});
