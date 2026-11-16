// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../plp/listing-grid", () => ({
  ListingGrid: ({
    listings,
    renderFooter,
  }: {
    listings: Array<{ title: string }>;
    renderFooter?: (listing: { title: string }) => React.ReactNode;
  }) => (
    <ul>
      {listings.map((l) => (
        <li key={l.title}>
          {l.title}
          {renderFooter?.(l)}
        </li>
      ))}
    </ul>
  ),
}));

import { StorefrontProducts, type StorefrontListing } from "./storefront-products";

afterEach(cleanup);

const listing = (title: string, slug: string | null, name: string | null): StorefrontListing => ({
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

describe("StorefrontProducts compare action", () => {
  it("shows 'Compare with other shops' only on listings other shops also sell", () => {
    render(
      <StorefrontProducts
        locale="en"
        listings={[
          {
            ...listing("Solar lamp", "solar", "Solar"),
            compare: {
              href: "/en/p/solar-lamp#compare",
              label: "Compare with 2 other shops · from K90.00",
              ariaLabel: "Compare Solar lamp at other shops",
            },
          },
          { ...listing("Phone charger", "phones", "Phones"), compare: null },
        ]}
        labels={labels}
        gridLabels={{} as never}
      />,
    );
    const links = screen.getAllByTestId("storefront-compare");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/en/p/solar-lamp#compare");
    expect(links[0]).toHaveTextContent("Compare with 2 other shops · from K90.00");
  });
});
