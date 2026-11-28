// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./search/search-input", () => ({
  SearchInput: ({ labels }: { labels: { placeholder: string } }) => (
    <input aria-label={labels.placeholder} data-testid="mock-search-input" />
  ),
}));

const usePathname = vi.fn(() => "/en");

vi.mock("next/navigation", () => ({
  usePathname: () => usePathname(),
}));

afterEach(cleanup);

import { MobileHeaderSearch } from "./mobile-header-search";

const labels = {
  placeholder: "Search Vergeo5",
  submit: "Search",
  ariaLabel: "Search",
  suggestionsLabel: "Suggestions",
  noSuggestions: "No suggestions",
  recentTitle: "Recent searches",
};

describe("MobileHeaderSearch", () => {
  it("renders nothing on the search results page", () => {
    usePathname.mockReturnValue("/en/search");
    const { container } = render(
      <MobileHeaderSearch
        locale="en"
        labels={labels}
        sheetTitle="Search"
        triggerLabel="Open search"
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the trigger on non-search shop routes", () => {
    usePathname.mockReturnValue("/en");
    render(
      <MobileHeaderSearch
        locale="en"
        labels={labels}
        sheetTitle="Search"
        triggerLabel="Open search"
      />,
    );
    expect(screen.getByTestId("mobile-header-search-trigger")).toBeInTheDocument();
  });

  it("opens a bottom sheet with SearchInput when the trigger is tapped", async () => {
    usePathname.mockReturnValue("/en");
    const user = userEvent.setup();
    render(
      <MobileHeaderSearch
        locale="en"
        labels={labels}
        sheetTitle="Search"
        triggerLabel="Open search"
      />,
    );

    await user.click(screen.getByTestId("mobile-header-search-trigger"));
    expect(screen.getByTestId("mobile-header-search-sheet")).toBeInTheDocument();
    expect(screen.getByTestId("mock-search-input")).toBeInTheDocument();
  });
});
