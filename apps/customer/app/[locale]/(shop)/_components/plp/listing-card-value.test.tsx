// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as deliveryEstimate from "../../../../../lib/delivery-estimate";

import { ListingCard, type ListingCardLabels } from "./listing-card";

import type { CatalogListing } from "./listing-grid";

vi.mock("../cart/mini-cart-drawer", () => ({
  addCartItem: vi.fn(),
  openMiniCart: vi.fn(),
  setLastAddedMessage: vi.fn(),
}));

vi.mock("./use-local-wishlist", () => ({
  useLocalWishlist: () => ({
    isWishlisted: false,
    toggleWishlist: vi.fn(),
    enabled: false,
  }),
}));

const baseLabels: ListingCardLabels = {
  vendor: "{vendor}",
  noReviews: "No reviews",
  reviewCount: "{count} reviews",
  quickAdd: "Add",
  wishlist: "Save",
  outOfStock: "Out",
  sellersFrom: "{count} sellers from {price}",
  deliversTodayPill: "Delivers today (Lusaka)",
};

function listing(overrides: Partial<CatalogListing> = {}): CatalogListing {
  return {
    id: "l1",
    title: "Phone",
    productSlug: "phone",
    vendorName: "Shop",
    priceNgwee: 250000,
    condition: "new",
    inStock: true,
    imagePublicId: null,
    rating: 0,
    reviewCount: 0,
    distanceM: null,
    belowMedian: false,
    deliveryAvailable: true,
    pickupAvailable: false,
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ListingCard value hints", () => {
  it("hides multiseller line when catalogue fields are absent", () => {
    render(<ListingCard locale="en" listing={listing()} labels={baseLabels} />);
    expect(screen.queryByTestId("listing-card-sellers-from")).not.toBeInTheDocument();
  });

  it("shows sellers-from when product-level fields exist", () => {
    render(
      <ListingCard
        locale="en"
        listing={listing({
          productSellerCount: 3,
          productLowestPriceNgwee: 245000,
        })}
        labels={baseLabels}
      />,
    );
    expect(screen.getByTestId("listing-card-sellers-from")).toHaveTextContent(
      "3 sellers from K2,450.00",
    );
  });

  it("shows delivers-today pill only for today delivery estimates", () => {
    vi.spyOn(deliveryEstimate, "estimateDelivery").mockReturnValue({
      kind: "delivery",
      when: "today",
    });
    render(<ListingCard locale="en" listing={listing()} labels={baseLabels} />);
    expect(screen.getByTestId("listing-card-delivers-today")).toBeInTheDocument();
  });
});
