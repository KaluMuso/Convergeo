// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ListingGrid } from "./plp/listing-grid";

vi.mock("@vergeo/ui/src/media/cloudinary-image", () => ({
  CloudinaryImage: ({ alt }: { alt: string }) => <img alt={alt} data-testid="cloudinary-image" />,
}));

afterEach(() => {
  cleanup();
});

const labels = {
  vendor: "Sold by {vendor}",
  noReviews: "No reviews yet",
  reviewCount: "{count} reviews",
  quickAdd: "Quick add",
  wishlist: "Save",
  outOfStock: "Out of stock",
  distance: "{distance} away",
  sampleListing: "Sample listing",
};

describe("ListingGrid demo disclosure (CUST-HOME-01)", () => {
  it("shows Sample listing only for demo/ media", () => {
    render(
      <ListingGrid
        locale="en"
        labels={labels}
        listings={[
          {
            id: "demo-1",
            title: "Demo phone",
            productSlug: "demo-phone",
            vendorName: "Sandbox",
            priceNgwee: 10000,
            condition: "new",
            inStock: true,
            imagePublicId: "demo/products/phone",
            rating: 0,
            reviewCount: 0,
            distanceM: null,
          },
          {
            id: "real-1",
            title: "Real phone",
            productSlug: "real-phone",
            vendorName: "Acme",
            priceNgwee: 20000,
            condition: "new",
            inStock: true,
            imagePublicId: "vendors/acme/phone",
            rating: 0,
            reviewCount: 0,
            distanceM: null,
          },
        ]}
      />,
    );

    expect(screen.getByText("Sample listing")).toBeInTheDocument();
    expect(screen.getAllByTestId("badge-sample")).toHaveLength(1);
  });

  it("hides Sample listing when the production gate is closed", () => {
    render(
      <ListingGrid
        locale="en"
        labels={labels}
        showSampleBadge={false}
        listings={[
          {
            id: "demo-1",
            title: "Demo phone",
            productSlug: "demo-phone",
            vendorName: "Sandbox",
            priceNgwee: 10000,
            condition: "new",
            inStock: true,
            imagePublicId: "demo/products/phone",
            rating: 0,
            reviewCount: 0,
            distanceM: null,
          },
        ]}
      />,
    );

    expect(screen.queryByText("Sample listing")).not.toBeInTheDocument();
    expect(screen.queryByTestId("badge-sample")).not.toBeInTheDocument();
  });
});
