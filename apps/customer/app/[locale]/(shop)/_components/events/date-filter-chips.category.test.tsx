import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { DateFilterChips } from "./date-filter-chips";
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/en/events",
  useSearchParams: () => new URLSearchParams("date_window=all&category=concerts&city=Lusaka"),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
const labels = {
  tonight: "Tonight",
  thisWeekend: "Weekend",
  nextWeek: "Week",
  nextMonth: "Month",
  allDates: "All dates",
  categoryLabel: "Category",
  subcategoryLabel: "Subcategory",
  calendarLabel: "Calendar",
  cityLabel: "City",
  cityPlaceholder: "City",
  neighbourhoodLabel: "Area",
  neighbourhoodPlaceholder: "Area",
  nearMe: "Near me",
  nearMeDenied: "Denied",
  categories: { all: "All", music: "Music", sports: "Sports" },
};
const props = {
  labels,
  calendarDates: [],
  categories: ["music", "sports"],
  activeDateWindow: "all" as const,
  activeOnDate: null,
  activeCategory: "concerts",
  activeCity: "Lusaka",
  activeNeighbourhood: "",
  nearMeActive: false,
};
const taxonomy = [
  { id: "music", parentId: null, label: "Music" },
  { id: "concerts", parentId: "music", label: "Concerts" },
  { id: "sports", parentId: null, label: "Sports" },
  { id: "football", parentId: "sports", label: "Football" },
];
it("hydrates deep category links and switches parent without retaining child while preserving other filters", () => {
  render(<DateFilterChips {...props} taxonomy={taxonomy} />);
  expect((screen.getByLabelText("Subcategory") as HTMLSelectElement).value).toBe("concerts");
  fireEvent.change(screen.getByLabelText("Category"), { target: { value: "sports" } });
  expect(replace).toHaveBeenCalledWith("/en/events?date_window=all&category=sports&city=Lusaka");
});
it("clears the parent and category query while retaining other filters", () => {
  render(<DateFilterChips {...props} taxonomy={taxonomy} />);
  fireEvent.change(screen.getByLabelText("Category"), { target: { value: "" } });
  expect(replace).toHaveBeenCalledWith("/en/events?date_window=all&city=Lusaka");
});
it("retains existing category chips when taxonomy read is unavailable or empty", () => {
  render(<DateFilterChips {...props} taxonomy={[]} />);
  expect(screen.queryByLabelText("Subcategory")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Sports" }));
  expect(replace).toHaveBeenCalledWith("/en/events?date_window=all&category=sports&city=Lusaka");
});
