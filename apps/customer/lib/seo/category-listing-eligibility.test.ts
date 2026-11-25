import { describe, expect, it } from "vitest";

import { categoryPathsEligibleForSitemap, categoryPlpRobots } from "./category-listing-eligibility";

describe("categoryPlpRobots", () => {
  it("noindexes empty categories but keeps follow", () => {
    expect(categoryPlpRobots(false, 0)).toEqual({ index: false, follow: true });
  });

  it("indexes categories with listings when unfiltered", () => {
    expect(categoryPlpRobots(false, 3)).toEqual({ index: true, follow: true });
  });

  it("noindexes filtered PLPs even with listings", () => {
    expect(categoryPlpRobots(true, 10)).toEqual({ index: false, follow: true });
  });
});

describe("categoryPathsEligibleForSitemap", () => {
  const categories = [
    { path: "electronics", prohibited: false },
    { path: "electronics/phones", prohibited: false },
    { path: "fashion-beauty", prohibited: false },
    { path: "prohibited-stuff", prohibited: true },
  ] as const;

  it("omits empty categories and keeps a parent when a child has listings", () => {
    const rows = categoryPathsEligibleForSitemap(categories, [
      {
        category_path: "electronics/phones",
        updated_at: "2026-11-20T10:00:00.000Z",
      },
    ]);
    expect(rows.map((row) => row.path)).toEqual(["electronics", "electronics/phones"]);
    expect(rows[1]?.lastModified?.toISOString()).toBe("2026-11-20T10:00:00.000Z");
    expect(rows.some((row) => row.path === "fashion-beauty")).toBe(false);
  });

  it("ignores listing paths outside the category tree and prohibited nodes", () => {
    const rows = categoryPathsEligibleForSitemap(categories, [
      {
        category_path: "prohibited-stuff",
        updated_at: "2026-11-20T10:00:00.000Z",
      },
      {
        category_path: "unknown/leaf",
        updated_at: "2026-11-20T10:00:00.000Z",
      },
    ]);
    expect(rows).toEqual([]);
  });
});
