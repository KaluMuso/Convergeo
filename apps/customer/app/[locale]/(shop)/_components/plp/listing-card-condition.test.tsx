// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./use-local-wishlist", () => ({
  useLocalWishlist: () => ({
    isWishlisted: false,
    toggleWishlist: vi.fn(),
    enabled: false,
  }),
}));

import { ListingCard, listingConditionLabel } from "./listing-card";

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
  conditionNew: "New",
  conditionRefurbished: "Refurbished",
};

describe("listingConditionLabel", () => {
  it("maps known conditions and omits unknown values", () => {
    expect(listingConditionLabel("new", labels)).toBe("New");
    expect(listingConditionLabel("refurbished", labels)).toBe("Refurbished");
    expect(listingConditionLabel("used", labels)).toBeUndefined();
    expect(listingConditionLabel("new", {})).toBeUndefined();
  });
});

describe("ListingCard condition meta", () => {
  it("shows refurbished condition in the meta slot", () => {
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
          condition: "refurbished",
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
    expect(screen.getByTestId("listing-card-condition")).toHaveTextContent("Refurbished");
  });

  it("omits condition meta when the value is unknown", () => {
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
          condition: "open_box",
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
    expect(screen.queryByTestId("listing-card-condition")).not.toBeInTheDocument();
  });
});
