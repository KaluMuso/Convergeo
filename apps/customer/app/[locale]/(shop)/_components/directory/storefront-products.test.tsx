// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../plp/listing-grid", () => ({
  ListingGrid: ({ listings }: { listings: Array<{ title: string }> }) => (
    <ul>
      {listings.map((l) => (
        <li key={l.title}>{l.title}</li>
      ))}
    </ul>
  ),
}));

import {
  StorefrontProducts,
  type StorefrontListing,
} from "./storefront-products";

afterEach(cleanup);

const listing = (
  title: string,
  slug: string | null,
  name: string | null,
): StorefrontListing => ({
  id: title,
  title,
  productSlug: title,
  vendorName: "Shop",
  priceNgwee: 1000,
  condition: "new",
  inStock: true,
  imagePublicId: null,
  rating: 0,
  reviewCount: 0,
  distanceM: null,
  belowMedian: false,
  deliveryAvailable: false,
  pickupAvailable: true,
  categorySlug: slug,
  categoryName: name,
});

const listings = [
  listing("Solar lamp", "solar", "Solar"),
  listing("Solar panel 200W", "solar", "Solar"),
  listing("Phone charger", "phones", "Phones"),
];
const labels = {
  search: "Search Shop",
  all: "All",
  noMatches: "No products match.",
};

describe("StorefrontProducts", () => {
  it("filters by category chip and in-store search", () => {
    render(
      <StorefrontProducts
        locale="en"
        listings={listings}
        gridLabels={{} as never}
        labels={labels}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Phones" }));
    expect(screen.getByText("Phone charger")).toBeInTheDocument();
    expect(screen.queryByText("Solar lamp")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    fireEvent.change(screen.getByPlaceholderText("Search Shop"), {
      target: { value: "panel" },
    });
    expect(screen.getByText("Solar panel 200W")).toBeInTheDocument();
    expect(screen.queryByText("Phone charger")).not.toBeInTheDocument();
  });

  it("shows an empty-match message", () => {
    render(
      <StorefrontProducts
        locale="en"
        listings={listings}
        gridLabels={{} as never}
        labels={labels}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText("Search Shop"), {
      target: { value: "zzz" },
    });
    expect(screen.getByRole("status")).toHaveTextContent("No products match.");
  });
});
