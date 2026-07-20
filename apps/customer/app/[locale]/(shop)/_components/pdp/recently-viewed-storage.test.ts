// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";

import {
  recentlyViewedExcluding,
  recordRecentlyViewed,
  RECENTLY_VIEWED_STORAGE_KEY,
} from "./recently-viewed-storage";

afterEach(() => {
  window.localStorage.clear();
});

describe("recently-viewed-storage", () => {
  it("records views and excludes the current product", () => {
    recordRecentlyViewed({
      slug: "a",
      name: "A",
      imagePublicId: null,
      fromPriceNgwee: 100,
    });
    recordRecentlyViewed({
      slug: "b",
      name: "B",
      imagePublicId: "img",
      fromPriceNgwee: 200,
    });

    const forB = recentlyViewedExcluding("b");
    expect(forB.map((item) => item.slug)).toEqual(["a"]);
    expect(window.localStorage.getItem(RECENTLY_VIEWED_STORAGE_KEY)).toContain('"slug":"b"');
  });

  it("moves a revisited product to the front", () => {
    recordRecentlyViewed({
      slug: "a",
      name: "A",
      imagePublicId: null,
      fromPriceNgwee: null,
    });
    recordRecentlyViewed({
      slug: "b",
      name: "B",
      imagePublicId: null,
      fromPriceNgwee: null,
    });
    recordRecentlyViewed({
      slug: "a",
      name: "A updated",
      imagePublicId: null,
      fromPriceNgwee: 50,
    });

    const items = recentlyViewedExcluding("x");
    expect(items[0]?.slug).toBe("a");
    expect(items[0]?.name).toBe("A updated");
  });
});
