// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import servicesMessages from "../../../../../../../packages/i18n/messages/en/services.json";
import { NO_FILTERS } from "../_lib/filters";

import { ServiceFilterBoxes, type FilterBoxLabels } from "./service-filter-boxes";
import { SERVICE_VERTICALS } from "./service-verticals";

const b = servicesMessages.browse;
const f = b.filters;
const labels: FilterBoxLabels = {
  heading: f.heading,
  more: f.more,
  clear: f.clear,
  remove: f.remove,
  results: "",
  area: f.area,
  areaAll: f.areaAll,
  areaPlaceholder: b.areaPlaceholder,
  filterSubmit: b.filterSubmit,
  price: f.price,
  priceAny: f.priceAny,
  priceBands: f.priceBands,
  rating: f.rating,
  ratingAny: f.ratingAny,
  ratingOptions: f.ratingOptions,
  availability: f.availability,
  availabilityAny: f.availabilityAny,
  availabilityNow: f.availabilityNow,
  all: servicesMessages.categories.all,
  categories: servicesMessages.categories,
};

afterEach(cleanup);

function renderBoxes(filters = NO_FILTERS, areas: (string | null)[] = []) {
  return render(
    <ServiceFilterBoxes
      locale="en"
      filters={filters}
      verticals={[...SERVICE_VERTICALS]}
      areas={areas}
      labels={labels}
    />,
  );
}

describe("ServiceFilterBoxes", () => {
  it("renders a card for every vertical, including the six new ones", () => {
    renderBoxes();
    for (const v of SERVICE_VERTICALS) {
      expect(screen.getByTestId(`filter-vertical-${v}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("filter-vertical-lodging")).toHaveTextContent("Hotels & lodges");
  });

  it("builds URL-synced links that keep the other filters", () => {
    renderBoxes({ ...NO_FILTERS, category: "lodging", avail: true });
    expect(screen.getByTestId("filter-band-mid")).toHaveAttribute(
      "href",
      "/en/services?category=lodging&band=mid&avail=1",
    );
    expect(screen.getByTestId("filter-rating-4")).toHaveAttribute(
      "href",
      "/en/services?category=lodging&rating=4&avail=1",
    );
    // Selecting the active vertical toggles it off.
    expect(screen.getByTestId("filter-vertical-lodging")).toHaveAttribute(
      "href",
      "/en/services?avail=1",
    );
  });

  it("marks the active vertical and shows removable chips with clear-all", () => {
    renderBoxes({ ...NO_FILTERS, category: "fitness", band: "high", rating: "45" });
    expect(screen.getByTestId("filter-vertical-fitness")).toHaveAttribute("aria-current", "true");
    const chips = within(screen.getByTestId("active-filters"));
    expect(chips.getByRole("link", { name: "Remove filter: Gyms & fitness" })).toHaveAttribute(
      "href",
      "/en/services?band=high&rating=45",
    );
    expect(chips.getByRole("link", { name: "Remove filter: K500 to K2,000" })).toBeInTheDocument();
    expect(chips.getByRole("link", { name: "Clear all" })).toHaveAttribute("href", "/en/services");
  });

  it("offers area chips from the results and a free-text area form keeping filters", () => {
    renderBoxes({ ...NO_FILTERS, category: "beauty" }, ["Lusaka, Rhodes Park", "Lusaka", "Ndola"]);
    expect(screen.getByRole("link", { name: "Lusaka" })).toHaveAttribute(
      "href",
      "/en/services?category=beauty&area=Lusaka",
    );
    const hidden = document.querySelector('form input[name="category"]');
    expect(hidden).toHaveAttribute("value", "beauty");
  });

  it("shows no chips row when nothing is filtered", () => {
    renderBoxes();
    expect(screen.queryByTestId("active-filters")).toBeNull();
  });
});
