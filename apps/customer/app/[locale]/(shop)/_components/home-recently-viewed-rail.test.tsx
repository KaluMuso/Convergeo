// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { HomeRecentlyViewedRail } from "./home-recently-viewed-rail";
import {
  RECENTLY_VIEWED_STORAGE_KEY,
  resetRecentlyViewedStoreForTests,
} from "./recently-viewed/use-recently-viewed";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  resetRecentlyViewedStoreForTests();
});

beforeEach(() => {
  window.localStorage.clear();
  resetRecentlyViewedStoreForTests();
});

const labels = {
  title: "Recently viewed",
  viewAll: "View all",
  viewProduct: "View {name}",
  view: "View",
};

describe("HomeRecentlyViewedRail", () => {
  it("renders nothing when history is empty", () => {
    const { container } = render(<HomeRecentlyViewedRail locale="en" labels={labels} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a horizontal rail from localStorage entries", async () => {
    window.localStorage.setItem(
      RECENTLY_VIEWED_STORAGE_KEY,
      JSON.stringify([
        { slug: "itel-a70", name: "Itel A70", viewedAt: 2 },
        { slug: "chitenge-wrap", name: "Chitenge wrap", viewedAt: 1 },
      ]),
    );

    render(<HomeRecentlyViewedRail locale="en" labels={labels} />);

    await waitFor(() => {
      expect(screen.getByTestId("home-recently-viewed-rail")).toBeInTheDocument();
    });
    expect(screen.getByText("Itel A70")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View all" })).toHaveAttribute(
      "href",
      "/en/account/recent",
    );
    expect(screen.getByRole("link", { name: "View Itel A70" })).toHaveAttribute(
      "href",
      "/en/p/itel-a70",
    );
  });
});
