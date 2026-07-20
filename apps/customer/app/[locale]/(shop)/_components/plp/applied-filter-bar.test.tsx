// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AppliedFilterBar } from "./applied-filter-bar";

afterEach(cleanup);

const labels = {
  ariaLabel: "Applied filters",
  clearAll: "Clear all",
  removeChip: "Remove filter {filter}",
  priceRange: "K{min} – K{max}",
  minPriceOnly: "From K{min}",
  maxPriceOnly: "Up to K{max}",
  conditionNew: "New",
  conditionRefurbished: "Refurbished",
  inStock: "In stock",
  outOfStock: "Out of stock",
  rating4Plus: "4★ & up",
  rating3Plus: "3★ & up",
  nearMe: "Near me",
  radiusKm: "Within {km} km",
};

describe("AppliedFilterBar", () => {
  it("renders nothing when no filters are active", () => {
    const { container } = render(
      <AppliedFilterBar
        pathname="/en/c/electronics"
        searchParams={new URLSearchParams()}
        filterState={{ condition: [], availability: [] }}
        labels={labels}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders removable chips and clear-all for active filters", () => {
    render(
      <AppliedFilterBar
        pathname="/en/c/electronics"
        searchParams={new URLSearchParams("condition=new&min_price=10&sort=newest")}
        filterState={{
          condition: ["new"],
          availability: [],
          minPrice: "10",
        }}
        labels={labels}
      />,
    );

    expect(screen.getByTestId("plp-applied-filters")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Clear all" })).toHaveAttribute(
      "href",
      "/en/c/electronics?sort=newest",
    );
    expect(screen.getByRole("link", { name: "Remove filter New" })).toHaveAttribute(
      "href",
      "/en/c/electronics?min_price=10&sort=newest",
    );
    expect(screen.getByRole("link", { name: "Remove filter From K10" })).toHaveAttribute(
      "href",
      "/en/c/electronics?condition=new&sort=newest",
    );
  });
});
