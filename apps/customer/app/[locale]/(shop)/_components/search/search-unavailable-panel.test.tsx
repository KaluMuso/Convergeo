// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SearchUnavailablePanel } from "./search-unavailable-panel";

const labels = {
  title: "Search unavailable",
  body: "Try again or browse.",
  retry: "Try again",
  browseHeading: "Browse instead",
};

const chips = [
  { key: "categories", href: "/en/categories", label: "Categories" },
  { key: "directory", href: "/en/directory", label: "Directory" },
];

afterEach(() => {
  cleanup();
});

describe("SearchUnavailablePanel", () => {
  it("renders retry and browse discovery chips", () => {
    render(
      <SearchUnavailablePanel
        retryHref="/en/search?q=phone"
        labels={labels}
        chips={chips}
        browseAriaLabel="Browse Vergeo5"
      />,
    );

    expect(screen.getByTestId("search-unavailable")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute(
      "href",
      "/en/search?q=phone",
    );
    expect(screen.getByText("Browse instead")).toBeInTheDocument();
    expect(screen.getByTestId("browse-discovery-chips")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Categories" })).toHaveAttribute(
      "href",
      "/en/categories",
    );
  });
});
