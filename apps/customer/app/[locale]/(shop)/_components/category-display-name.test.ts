import { describe, expect, it } from "vitest";

import { resolveFacetCategoryLabel, slugToCategoryLabel } from "./category-display-name";

describe("slugToCategoryLabel", () => {
  it("title-cases hyphenated slugs", () => {
    expect(slugToCategoryLabel("tech-services")).toBe("Tech Services");
  });
});

describe("resolveFacetCategoryLabel", () => {
  it("prefers known labels then falls back", () => {
    expect(resolveFacetCategoryLabel("groceries", { groceries: "Groceries" })).toBe("Groceries");
    expect(resolveFacetCategoryLabel("unknown-vertical", {})).toBe("Unknown Vertical");
  });
});
