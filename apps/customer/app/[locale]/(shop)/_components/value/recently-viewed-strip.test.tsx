// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  RECENTLY_VIEWED_STORAGE_KEY,
  resetRecentlyViewedStoreForTests,
} from "../recently-viewed/use-recently-viewed";

import { RecentlyViewedStripClient } from "./recently-viewed-strip.client";

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
  viewProduct: "View {name}",
};

describe("RecentlyViewedStripClient", () => {
  it("excludes the current slug and caps at six", async () => {
    const entries = Array.from({ length: 8 }, (_, index) => ({
      slug: `item-${index}`,
      name: `Item ${index}`,
      viewedAt: index,
      priceNgwee: 10000 + index,
    }));
    window.localStorage.setItem(RECENTLY_VIEWED_STORAGE_KEY, JSON.stringify(entries));

    render(<RecentlyViewedStripClient locale="en" currentSlug="item-0" labels={labels} />);

    await waitFor(() => {
      expect(screen.getByTestId("value-recently-viewed-strip")).toBeInTheDocument();
    });
    const links = screen.getAllByRole("link");
    expect(links.length).toBe(6);
    expect(screen.queryByRole("link", { name: "View Item 0" })).not.toBeInTheDocument();
    expect(screen.getByText("K100.06")).toBeInTheDocument();
  });
});
