// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  recordRecentlyViewed,
  RECENTLY_VIEWED_STORAGE_KEY,
  resetRecentlyViewedStoreForTests,
} from "../recently-viewed/use-recently-viewed";

import { RecentlyViewedStripClient } from "./recently-viewed-strip.client";

afterEach(() => {
  resetRecentlyViewedStoreForTests();
  window.localStorage.removeItem(RECENTLY_VIEWED_STORAGE_KEY);
});

describe("RecentlyViewedStripClient", () => {
  it("hides the current slug and caps at six", () => {
    for (let i = 0; i < 8; i += 1) {
      recordRecentlyViewed(`p-${i}`, `Product ${i}`, 1_000 * (i + 1));
    }
    render(
      <RecentlyViewedStripClient
        locale="en"
        currentSlug="p-3"
        labels={{ title: "Recently viewed", viewProduct: "View {name}" }}
      />,
    );
    expect(screen.queryByText("Product 3")).not.toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(6);
  });
});
