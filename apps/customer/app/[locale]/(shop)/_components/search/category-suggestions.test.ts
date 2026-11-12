import { describe, expect, it } from "vitest";

import { buildTopCategorySuggestions } from "./category-suggestions";

import type { CategoryRow } from "../merch-data";

function row(overrides: Partial<CategoryRow> & Pick<CategoryRow, "slug">): CategoryRow {
  return {
    id: overrides.slug,
    name: overrides.slug.toUpperCase(),
    path: overrides.slug,
    position: 0,
    parent_id: null,
    prohibited: false,
    ...overrides,
  };
}

describe("buildTopCategorySuggestions", () => {
  it("returns the first four root categories by position with locale-prefixed hrefs", () => {
    const result = buildTopCategorySuggestions(
      [
        row({ slug: "e", position: 5 }),
        row({ slug: "a", position: 1 }),
        row({ slug: "child", position: 0, parent_id: "a" }),
        row({ slug: "banned", position: 0, prohibited: true }),
        row({ slug: "b", position: 2, name: "Beauty" }),
        row({ slug: "c", position: 3 }),
        row({ slug: "d", position: 4 }),
      ],
      "fr",
    );

    expect(result.map((item) => item.key)).toEqual(["a", "b", "c", "d"]);
    expect(result[1]).toEqual({ key: "b", href: "/fr/c/b", label: "Beauty" });
  });

  it("returns an empty list (graceful empty state) when there are no usable roots", () => {
    expect(buildTopCategorySuggestions([], "en")).toEqual([]);
    expect(buildTopCategorySuggestions([row({ slug: "x", parent_id: "y" })], "en")).toEqual([]);
  });
});
