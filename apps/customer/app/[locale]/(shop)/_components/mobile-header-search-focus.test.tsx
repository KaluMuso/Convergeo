// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * The real SearchInput forwards `autoFocus` to its <input>. The mock honours it
 * so this suite reproduces the regression it guards: an input that focuses
 * itself on mount beats the bottom sheet's focus trap to `document.activeElement`,
 * so the trap captures the input (not the trigger) as the element to restore to.
 * On dismiss it then restores focus to a detached node and the browser drops
 * focus to <body>, stranding keyboard users at the top of the document.
 */
vi.mock("./search/search-input", () => ({
  SearchInput: ({
    labels,
    autoFocus,
  }: {
    labels: { placeholder: string };
    autoFocus?: boolean;
  }) => (
    <input aria-label={labels.placeholder} data-testid="mock-search-input" autoFocus={autoFocus} />
  ),
}));

afterEach(cleanup);

import { MobileHeaderSearch } from "./mobile-header-search";

const labels = {
  placeholder: "Search Convergeo",
  submit: "Search",
  ariaLabel: "Search",
  suggestionsLabel: "Suggestions",
  noSuggestions: "No suggestions",
  recentTitle: "Recent searches",
};

function renderSearch() {
  return render(
    <MobileHeaderSearch
      locale="en"
      labels={labels}
      sheetTitle="Search"
      triggerLabel="Open search"
    />,
  );
}

describe("MobileHeaderSearch focus handling", () => {
  it("moves focus into the sheet on open", async () => {
    const user = userEvent.setup();
    renderSearch();

    await user.click(screen.getByTestId("mobile-header-search-trigger"));

    const sheet = screen.getByTestId("mobile-header-search-sheet");
    expect(sheet).toContainElement(document.activeElement as HTMLElement);
  });

  it("returns focus to the search trigger when the sheet is dismissed", async () => {
    const user = userEvent.setup();
    renderSearch();

    const trigger = screen.getByTestId("mobile-header-search-trigger");
    await user.click(trigger);
    expect(screen.getByTestId("mobile-header-search-sheet")).toBeInTheDocument();

    await user.keyboard("{Escape}");

    expect(screen.queryByTestId("mobile-header-search-sheet")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(trigger);
  });
});
