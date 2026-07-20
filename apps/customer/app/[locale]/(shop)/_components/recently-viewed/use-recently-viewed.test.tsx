// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  RECENTLY_VIEWED_MAX,
  recordRecentlyViewed,
  resetRecentlyViewedStoreForTests,
  upsertRecentlyViewed,
  useRecentlyViewed,
} from "./use-recently-viewed";

beforeEach(() => {
  window.localStorage.clear();
  resetRecentlyViewedStoreForTests();
});

afterEach(() => {
  window.localStorage.clear();
  resetRecentlyViewedStoreForTests();
});

describe("upsertRecentlyViewed", () => {
  it("deduplicates by slug and moves the latest view to the front", () => {
    const first = upsertRecentlyViewed([], {
      slug: "a",
      name: "A",
      viewedAt: 1,
    });
    const second = upsertRecentlyViewed(first, {
      slug: "b",
      name: "B",
      viewedAt: 2,
    });
    const again = upsertRecentlyViewed(second, {
      slug: "a",
      name: "A updated",
      viewedAt: 3,
    });

    expect(again.map((entry) => entry.slug)).toEqual(["a", "b"]);
    expect(again[0]?.name).toBe("A updated");
  });

  it("caps history at the max item count", () => {
    let entries: ReturnType<typeof upsertRecentlyViewed> = [];
    for (let index = 0; index < RECENTLY_VIEWED_MAX + 5; index += 1) {
      entries = upsertRecentlyViewed(entries, {
        slug: `slug-${index}`,
        name: `Name ${index}`,
        viewedAt: index,
      });
    }
    expect(entries).toHaveLength(RECENTLY_VIEWED_MAX);
    expect(entries[0]?.slug).toBe(`slug-${RECENTLY_VIEWED_MAX + 4}`);
  });
});

describe("useRecentlyViewed", () => {
  it("records and clears device-local history", () => {
    act(() => {
      recordRecentlyViewed("itel-a70", "Itel A70");
      recordRecentlyViewed("tecno-spark", "Tecno Spark");
      recordRecentlyViewed("itel-a70", "Itel A70");
    });

    const { result } = renderHook(() => useRecentlyViewed());
    expect(result.current.entries.map((entry) => entry.slug)).toEqual(["itel-a70", "tecno-spark"]);

    act(() => {
      result.current.clear();
    });
    expect(result.current.entries).toEqual([]);
  });
});
