// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../cart/mini-cart-drawer", () => ({
  addCartItem: vi.fn(),
  openMiniCart: vi.fn(),
  setLastAddedMessage: vi.fn(),
}));

vi.mock("./use-local-wishlist", () => ({
  useLocalWishlist: () => ({
    isWishlisted: false,
    toggleWishlist: vi.fn(),
    enabled: true,
  }),
}));

import { ListingCard } from "./listing-card";

afterEach(() => {
  cleanup();
});

const labels = {
  vendor: "Sold by {vendor}",
  noReviews: "No reviews",
  reviewCount: "({count})",
  quickAdd: "Quick add",
  wishlist: "Save",
  outOfStock: "Out of stock",
  logistics: {
    nearest: "{distance} away",
    belowMedian: "Below median",
    delivery: "Lusaka delivery",
    pickup: "Pickup available",
  },
};

describe("ListingCard link a11y", () => {
  it("does not nest wishlist inside the product link overlay", () => {
    render(
      <ListingCard
        locale="en"
        labels={labels}
        listing={{
          id: "listing-1",
          title: "Phone",
          productSlug: "phone",
          vendorName: "Alpha",
          priceNgwee: 100_000,
          condition: "new",
          inStock: true,
          imagePublicId: null,
          rating: 0,
          reviewCount: 0,
          distanceM: null,
          belowMedian: false,
          deliveryAvailable: false,
          pickupAvailable: false,
        }}
      />,
    );

    const link = screen.getByTestId("listing-card-link");
    const wishlist = screen.getByTestId("product-card-wishlist");
    expect(link).toHaveAttribute("href", "/en/p/phone");
    expect(link).not.toContainElement(wishlist);
  });
});
