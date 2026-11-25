import { describe, expect, it } from "vitest";
import { resolveFacetCategoryLabel, slugToCategoryLabel } from "./category-display-name";

describe("category display fallback", () => {
  it("title-cases slugs", () => {
    expect(slugToCategoryLabel("tech-services")).toBe("Tech Services");
  });
  it("resolves known labels", () => {
    expect(resolveFacetCategoryLabel("groceries", { groceries: "Groceries" })).toBe("Groceries");
  });
});
