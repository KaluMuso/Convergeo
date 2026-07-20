// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Comparison, type ComparisonLabels, type ComparisonListing } from "./comparison";

afterEach(() => {
  cleanup();
});

const labels: ComparisonLabels = {
  heading: "Compare sellers",
  vendorCount: "{count} sellers",
  sortLabel: "Sort by",
  sortPrice: "Lowest price",
  sortDistance: "Nearest",
  price: "Price",
  condition: "Condition",
  distance: "{distance} away",
  vendor: "Seller",
  fulfillment: "Options",
  delivery: "Delivery",
  pickup: "Pickup",
  selectListing: "Select",
  selectedListing: "Selected",
  preferredBadge: "Preferred seller",
  noReviews: "No reviews yet",
  rating: "{rating} ({count} reviews)",
  conditionNew: "New",
  conditionRefurbished: "Refurbished",
  usingFallbackLocation: "Distances from Lusaka CBD.",
};

const listings: ComparisonListing[] = [
  {
    id: "a",
    priceNgwee: 100_000,
    condition: "new",
    vendor: {
      id: "v1",
      slug: "alpha",
      displayName: "Alpha Shop",
      preferredBadge: true,
      ratingAvg: 4.5,
      ratingCount: 12,
      lat: -15.4,
      lng: 28.3,
      landmark: null,
    },
    deliveryAvailable: true,
    pickupAvailable: false,
  },
  {
    id: "b",
    priceNgwee: 90_000,
    condition: "refurbished",
    vendor: {
      id: "v2",
      slug: "beta",
      displayName: "Beta Mart",
      preferredBadge: false,
      ratingAvg: null,
      ratingCount: 0,
      lat: null,
      lng: null,
      landmark: null,
    },
    deliveryAvailable: false,
    pickupAvailable: true,
  },
];

describe("Comparison mobile cards", () => {
  it("renders seller cards and selects an offer", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();

    render(
      <Comparison listings={listings} selectedListingId="a" labels={labels} onSelect={onSelect} />,
    );

    expect(screen.getByTestId("pdp-compare-cards")).toBeInTheDocument();
    expect(screen.getByTestId("comparison-card-a")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("comparison-card-b")).toHaveAttribute("aria-pressed", "false");

    await user.click(screen.getByTestId("comparison-card-b"));
    expect(onSelect).toHaveBeenCalledWith("b");
  });
});
