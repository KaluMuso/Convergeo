import { describe, expect, it } from "vitest";

import {
  appendSearchFiltersToApiParams,
  buildSearchFilterChips,
  clearSearchFiltersHref,
  decodeSearchFilters,
  encodeSearchFilters,
  formatCategoryPathLabel,
  hasActiveSearchFilters,
  hrefWithoutSearchFilterChip,
} from "./search-filters";

describe("search-filters", () => {
  it("round-trips URL params", () => {
    const state = {
      minPrice: "400000",
      maxPrice: "900000",
      categoryPath: "electronics/phones",
    };
    const encoded = encodeSearchFilters(state);
    expect(decodeSearchFilters(encoded)).toEqual(state);
  });

  it("maps filters to search API params", () => {
    const api = new URLSearchParams({ q: "phone" });
    appendSearchFiltersToApiParams(api, {
      minPrice: "100",
      maxPrice: "500",
      categoryPath: "electronics",
    });
    expect(api.get("price_min_ngwee")).toBe("100");
    expect(api.get("price_max_ngwee")).toBe("500");
    expect(api.get("category_path")).toBe("electronics");
  });

  it("builds chips and clear/remove hrefs", () => {
    const state = {
      minPrice: "10",
      categoryPath: "electronics/phones",
    };
    expect(hasActiveSearchFilters(state)).toBe(true);
    const chips = buildSearchFilterChips(state, { "electronics/phones": "Phones" });
    expect(chips).toHaveLength(2);

    const base = new URLSearchParams("q=phone&min_price=10&category_path=electronics/phones");
    expect(hrefWithoutSearchFilterChip("/en/search", base, chips[0]!)).toBe(
      "/en/search?q=phone&category_path=electronics%2Fphones",
    );
    expect(clearSearchFiltersHref("/en/search", base)).toBe("/en/search?q=phone");
  });

  it("formats category path labels", () => {
    expect(formatCategoryPathLabel("home-living")).toBe("Home Living");
    expect(formatCategoryPathLabel("electronics/phones")).toBe("Phones");
  });
});
