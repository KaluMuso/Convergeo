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

describe("RecentlyViewedStripClient", () => {
  it("excludes the current slug and caps at six", async () => {
    const entries = Array.from({ length: 8 }, (_, i) => ({
      slug: `item-${i}`,
      name: `Item ${i}`,
      viewedAt: i,
      priceNgwee: 10000 + i,
    }));
    window.localStorage.setItem(RECENTLY_VIEWED_STORAGE_KEY, JSON.stringify(entries));
    render(
      <RecentlyViewedStripClient
        locale="en"
        currentSlug="item-0"
        labels={{ title: "Recent", viewProduct: "View {name}" }}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("value-recently-viewed-strip")).toBeInTheDocument(),
    );
    expect(screen.getAllByRole("link")).toHaveLength(6);
    expect(screen.queryByRole("link", { name: "View Item 0" })).not.toBeInTheDocument();
  });
});
