// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@vergeo/ui/src/media/cloudinary-image-static", () => ({
  CloudinaryImageStatic: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

import { ListingGrid, type CatalogListing } from "./listing-grid";

afterEach(() => {
  cleanup();
});

const labels = {
  vendor: "Sold by {vendor}",
  noReviews: "No reviews yet",
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

function listing(overrides: Partial<CatalogListing> = {}): CatalogListing {
  return {
    id: "listing-1",
    title: "Demo item",
    productSlug: "demo-item",
    vendorName: "Kabwata Market",
    priceNgwee: 100_00,
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

describe("ListingGrid", () => {
  it("links to the product when a slug exists", () => {
    render(<ListingGrid locale="en" listings={[listing()]} labels={labels} />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/en/p/demo-item");
  });

  it("uses a denser five-column marketplace grid at wide desktop", () => {
    render(<ListingGrid locale="en" listings={[listing()]} labels={labels} density="compact" />);
    const grid = screen.getByTestId("listing-grid");
    expect(grid).toHaveClass("gap-2", "xl:grid-cols-5");
    expect(screen.getByTestId("product-card")).toHaveAttribute("data-density", "compact");
  });

  it("does not invent a /c/all href when productSlug is null", () => {
    render(<ListingGrid locale="en" listings={[listing({ productSlug: null })]} labels={labels} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByTestId("listing-card-no-slug")).toBeInTheDocument();
  });
});
