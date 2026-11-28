import { describe, expect, it } from "vitest";

import {
  activeCount,
  areaOptions,
  hrefFor,
  NO_FILTERS,
  parseFilters,
  toApiQuery,
  withPatch,
} from "./filters";

describe("parseFilters", () => {
  it("accepts known values and rejects junk", () => {
    expect(
      parseFilters({
        category: "lodging",
        area: " Lusaka ",
        band: "mid",
        rating: "45",
        avail: "1",
      }),
    ).toEqual({ category: "lodging", area: "Lusaka", band: "mid", rating: "45", avail: true });
    expect(parseFilters({ category: "weapons", band: "cheap", rating: "9", avail: "yes" })).toEqual(
      NO_FILTERS,
    );
  });

  it("accepts every new vertical", () => {
    for (const v of ["lodging", "property", "fitness", "rentals", "family-fun", "staffing"]) {
      expect(parseFilters({ category: v }).category).toBe(v);
    }
  });
});

describe("toApiQuery", () => {
  it("maps bands to integer ngwee bounds and ratings to numbers", () => {
    const q = new URLSearchParams(
      toApiQuery({ ...NO_FILTERS, band: "mid", rating: "45", avail: true, category: "fitness" }),
    );
    expect(q.get("price_min")).toBe("10000");
    expect(q.get("price_max")).toBe("50000");
    expect(q.get("min_rating")).toBe("4.5");
    expect(q.get("available")).toBe("true");
    expect(q.get("category")).toBe("fitness");
  });

  it("leaves open-ended bands open and omits empty filters", () => {
    expect(toApiQuery({ ...NO_FILTERS, band: "premium" })).toBe("price_min=200001");
    expect(toApiQuery({ ...NO_FILTERS, band: "under100" })).toBe("price_max=9999");
    expect(toApiQuery(NO_FILTERS)).toBe("");
  });
});

describe("hrefFor / withPatch", () => {
  it("round-trips through the URL and drops cleared values", () => {
    const filters = withPatch(NO_FILTERS, { category: "beauty", band: "high", avail: true });
    const href = hrefFor("en", filters);
    expect(href).toBe("/en/services?category=beauty&band=high&avail=1");
    expect(hrefFor("en", withPatch(filters, { band: null, avail: false }))).toBe(
      "/en/services?category=beauty",
    );
    expect(hrefFor("fr", NO_FILTERS)).toBe("/fr/services");
  });

  it("counts active filters", () => {
    expect(activeCount(NO_FILTERS)).toBe(0);
    expect(activeCount({ ...NO_FILTERS, area: "Kitwe", rating: "3", avail: true })).toBe(3);
  });
});

describe("areaOptions", () => {
  it("uses the first segment, most common first, capped", () => {
    expect(areaOptions(["Lusaka, Kabulonga", "Lusaka", "Ndola", null, "  ", "Kitwe"], 2)).toEqual([
      "Lusaka",
      "Kitwe",
    ]);
  });
});
