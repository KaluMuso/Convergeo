// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  BROWSED_CATEGORIES_KEY,
  BROWSED_CATEGORIES_MAX,
  readBrowsedCategories,
  recordBrowsedCategory,
} from "./browsed-categories";

beforeEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("browsed categories", () => {
  it("records most-recent-first, de-duplicates by href and caps the list", () => {
    for (let i = 0; i < BROWSED_CATEGORIES_MAX + 3; i += 1) {
      recordBrowsedCategory({ slug: `c${i}`, label: `C${i}`, href: `/en/c/c${i}` });
    }
    recordBrowsedCategory({ slug: "c5", label: "C5", href: "/en/c/c5" });
    const list = readBrowsedCategories();
    expect(list).toHaveLength(BROWSED_CATEGORIES_MAX);
    expect(list[0]?.slug).toBe("c5");
    expect(list.filter((entry) => entry.slug === "c5")).toHaveLength(1);
  });

  it("ignores malformed storage and non-local hrefs", () => {
    window.localStorage.setItem(
      BROWSED_CATEGORIES_KEY,
      JSON.stringify([{ slug: "x", label: "X", href: "https://evil.example" }, 4, null]),
    );
    expect(readBrowsedCategories()).toEqual([]);
    window.localStorage.setItem(BROWSED_CATEGORIES_KEY, "{not json");
    expect(readBrowsedCategories()).toEqual([]);
  });

  it("never throws when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readBrowsedCategories()).toEqual([]);
    expect(() => recordBrowsedCategory({ slug: "a", label: "A", href: "/en/c/a" })).not.toThrow();
  });
});
