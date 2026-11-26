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
    expect(grid).toHaveClass("gap-3", "xl:grid-cols-5");
    expect(screen.getByTestId("product-card")).toHaveAttribute("data-density", "compact");
  });

  it("is 2 columns at 360px and steps up to 5 on wide desktop", () => {
    render(<ListingGrid locale="en" listings={[listing()]} labels={labels} />);
    expect(screen.getByTestId("listing-grid")).toHaveClass(
      "grid-cols-2",
      "md:grid-cols-3",
      "lg:grid-cols-4",
      "xl:grid-cols-5",
    );
    expect(screen.getByTestId("listing-grid").className).not.toContain("2xl:grid-cols-6");
  });

  it("renders a snap-scrolling single-row list in rail layout", () => {
    render(
      <ListingGrid
        locale="en"
        layout="rail"
        listings={[listing(), listing({ id: "listing-2", title: "Second" })]}
        labels={labels}
      />,
    );
    const rail = screen.getByTestId("listing-grid");
    expect(rail.tagName).toBe("UL");
    expect(rail).toHaveAttribute("data-layout", "rail");
    expect(rail).toHaveClass("flex", "overflow-x-auto", "snap-x");
    expect(rail).not.toHaveClass("grid");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("shows a discount badge and struck price only when a compare-at price exists", () => {
    render(
      <ListingGrid
        locale="en"
        listings={[
          listing({ id: "sale", title: "On sale", priceNgwee: 75_00, oldNgwee: 100_00 }),
          listing({ id: "full", title: "Full price" }),
        ]}
        labels={{ ...labels, discount: "−{percent}%" }}
      />,
    );
    const badges = screen.getAllByTestId("product-card-discount");
    expect(badges).toHaveLength(1);
    expect(badges[0]).toHaveTextContent("−25%");
    const struck = document.querySelectorAll(".line-through");
    expect(struck).toHaveLength(1);
    expect(struck[0]).toHaveTextContent("K100.00");
  });

  it("renders stars and a count only when the listing has reviews", () => {
    render(
      <ListingGrid
        locale="en"
        listings={[
          listing({ id: "r", title: "Reviewed", rating: 4.5, reviewCount: 12 }),
          listing({ id: "n", title: "Unreviewed" }),
        ]}
        labels={labels}
      />,
    );
    expect(screen.getByText("(12)")).toBeInTheDocument();
    expect(screen.queryByText("No reviews yet")).not.toBeInTheDocument();
  });

  it("drops the logistics pill row in dense cards but keeps it in the roomy layout", () => {
    const delivering = listing({ deliveryAvailable: true, pickupAvailable: true });
    const { rerender } = render(
      <ListingGrid locale="en" listings={[delivering]} labels={labels} />,
    );
    expect(screen.queryByText("Pickup available")).not.toBeInTheDocument();
    rerender(<ListingGrid locale="en" listings={[delivering]} labels={labels} density="default" />);
    expect(screen.getByText("Pickup available")).toBeInTheDocument();
  });

  it("links standalone listings by listing id when productSlug is null", () => {
    render(<ListingGrid locale="en" listings={[listing({ productSlug: null })]} labels={labels} />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/en/l/listing-1");
  });
});
