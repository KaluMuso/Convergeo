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

import { ListingCard } from "./listing-card";

afterEach(cleanup);

/** Labels arrive as literal ICU templates; the card interpolates them. */
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
  conditionUsed: "Used",
};

const listing = {
  id: "listing-1",
  title: "Solar lamp",
  productSlug: "solar-lamp",
  vendorName: "Kabwata Electronics",
  priceNgwee: 24_900,
  condition: "new",
  inStock: true,
  imagePublicId: null,
  rating: 4.6,
  reviewCount: 38,
  distanceM: null,
  belowMedian: false,
  deliveryAvailable: false,
  pickupAvailable: false,
};

describe("ListingCard template labels", () => {
  /**
   * Regression: the review-count template was handed to the card unchanged, so
   * shoppers saw a literal "({count})" beside the stars instead of the number.
   */
  it("substitutes the review count into its template", () => {
    render(<ListingCard locale="en" labels={labels} listing={listing} />);

    expect(screen.getByText("(38)")).toBeInTheDocument();
    expect(screen.queryByText("({count})")).not.toBeInTheDocument();
  });

  it("substitutes the seller name into its template", () => {
    render(<ListingCard locale="en" labels={labels} listing={listing} />);

    expect(screen.getByText("Sold by Kabwata Electronics")).toBeInTheDocument();
    expect(screen.queryByText("Sold by {vendor}")).not.toBeInTheDocument();
  });
});
