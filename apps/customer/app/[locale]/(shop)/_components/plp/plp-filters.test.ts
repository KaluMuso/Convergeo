import { describe, expect, it } from "vitest";

import { buildAppliedFilterChips, decodePlpFilters, hasActivePlpFilters } from "./plp-filters";

describe("buildAppliedFilterChips", () => {
  it("is empty for a blank filter state", () => {
    expect(
      buildAppliedFilterChips({
        condition: [],
        availability: [],
      }),
    ).toEqual([]);
    expect(hasActivePlpFilters({ condition: [], availability: [] })).toBe(false);
  });

  it("emits chips for price, condition, availability, rating, and location", () => {
    const chips = buildAppliedFilterChips({
      minPrice: "10",
      maxPrice: "50",
      condition: ["new", "refurbished"],
      availability: ["in_stock"],
      minRating: "4",
      lat: "-15.4",
      lng: "28.3",
      radiusKm: "5",
    });

    expect(chips.map((chip) => chip.id)).toEqual([
      "price",
      "condition:new",
      "condition:refurbished",
      "availability:in_stock",
      "rating:4",
      "location",
    ]);
    expect(hasActivePlpFilters(decodePlpFilters(new URLSearchParams("condition=new")))).toBe(true);
  });
});
