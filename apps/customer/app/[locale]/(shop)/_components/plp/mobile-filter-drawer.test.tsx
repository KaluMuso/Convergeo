// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { testFilterLabels } from "../filters/test-labels";

import { MobileFilterDrawer } from "./mobile-filter-drawer";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/en/c/electronics",
  useSearchParams: () => new URLSearchParams(),
}));

afterEach(() => {
  cleanup();
});

const labels = { ...testFilterLabels, openFilters: "Filters", filtersActive: "Filters (active)" };

describe("MobileFilterDrawer", () => {
  it("opens the filter boxes from the mobile control", async () => {
    const user = userEvent.setup();
    render(
      <MobileFilterDrawer
        labels={labels}
        facets={{
          condition: [{ value: "used", count: 3 }],
          availability: [],
          rating: [],
        }}
        initialState={{ condition: [], availability: [] }}
      />,
    );

    expect(screen.queryByTestId("plp-filter-drawer")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("plp-open-filters"));
    expect(screen.getByTestId("plp-filter-drawer")).toBeInTheDocument();
    expect(screen.getByTestId("plp-facet-panel")).toBeInTheDocument();
    expect((await screen.findAllByTestId("filter-box")).length).toBeGreaterThan(3);
    expect(screen.getByText("Used")).toBeInTheDocument();
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
