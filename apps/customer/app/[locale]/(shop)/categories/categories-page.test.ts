import { describe, expect, it } from "vitest";

import { buildCategoryTree } from "../_components/category-mega-menu";

describe("categories browse tree (CUST-03)", () => {
  it("exposes Phase-1 roots with navigable children", () => {
    const tree = buildCategoryTree([
      {
        id: "electronics",
        name: "Electronics",
        slug: "electronics",
        position: 1,
        parent_id: null,
        prohibited: false,
      },
      {
        id: "phones",
        name: "Phones",
        slug: "phones",
        position: 1,
        parent_id: "electronics",
        prohibited: false,
      },
      {
        id: "banned",
        name: "Banned",
        slug: "banned",
        position: 2,
        parent_id: null,
        prohibited: true,
      },
    ]);

    expect(tree).toHaveLength(1);
    expect(tree[0]?.slug).toBe("electronics");
    expect(tree[0]?.children.map((child) => child.slug)).toEqual(["phones"]);
  });

  it("returns an empty tree honestly when there are no public categories", () => {
    expect(buildCategoryTree([])).toEqual([]);
  });
});
