// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MobileFilterDrawer } from "./mobile-filter-drawer";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/en/c/electronics",
  useSearchParams: () => new URLSearchParams(),
}));

afterEach(() => {
  cleanup();
});

const labels = {
  heading: "Filters",
  price: "Price",
  minPrice: "Min",
  maxPrice: "Max",
  condition: "Condition",
  conditionNew: "New",
  conditionRefurbished: "Refurbished",
  availability: "Availability",
  inStock: "In stock",
  outOfStock: "Out of stock",
  rating: "Rating",
  rating4Plus: "4+",
  rating3Plus: "3+",
  location: "Near me",
  radiusKm: "Within {km} km",
  apply: "Apply",
  clear: "Clear",
  openFilters: "Filters",
  filtersActive: "Filters (active)",
};

describe("MobileFilterDrawer", () => {
  it("opens the filter modal from the mobile control", async () => {
    const user = userEvent.setup();
    render(
      <MobileFilterDrawer
        labels={labels}
        facets={{ condition: [], availability: [], rating: [] }}
        initialState={{ condition: [], availability: [] }}
      />,
    );

    expect(screen.queryByTestId("plp-filter-drawer")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("plp-open-filters"));
    expect(screen.getByTestId("plp-filter-drawer")).toBeInTheDocument();
    expect(screen.getByTestId("plp-facet-panel")).toBeInTheDocument();
  });

  it("shows active label when filters are applied", () => {
    render(
      <MobileFilterDrawer
        labels={labels}
        facets={{ condition: [], availability: [], rating: [] }}
        initialState={{ condition: ["new"], availability: [] }}
      />,
    );
    expect(screen.getByTestId("plp-open-filters")).toHaveTextContent("Filters (active)");
  });
});
