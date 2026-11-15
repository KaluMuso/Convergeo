import { describe, expect, it } from "vitest";

import { categoryDisplayName } from "./category-tree";

const rows = [
  { slug: "mens-clothing", name: "Men's Clothing" },
  { slug: "fashion-beauty", name: "Fashion & Beauty" },
];

describe("categoryDisplayName", () => {
  it("uses the category's own name, not a title-cased slug", () => {
    expect(categoryDisplayName(rows, "mens-clothing")).toBe("Men's Clothing");
    expect(categoryDisplayName(rows, "fashion-beauty")).toBe("Fashion & Beauty");
  });

  it("falls back to a title-cased slug only for unknown categories", () => {
    expect(categoryDisplayName(rows, "home-garden")).toBe("Home Garden");
    expect(categoryDisplayName([], undefined)).toBe("");
  });
});
