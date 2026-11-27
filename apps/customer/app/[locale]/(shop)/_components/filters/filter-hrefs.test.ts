import { describe, expect, it } from "vitest";

import {
  activePriceBand,
  clearFiltersHref,
  hrefWith,
  inStockHref,
  nearMeActive,
  nearMeOffHref,
  nearMeOnHref,
  priceBandHref,
  ratingHref,
  toggleFlagHref,
} from "./filter-hrefs";

const P = (q: string) => new URLSearchParams(q);

describe("filter hrefs", () => {
  it("drops page and cursor on every change", () => {
    expect(hrefWith("/c/x", P("page=2&cursor=abc&sort=newest"), { deals: "1" })).toBe(
      "/c/x?sort=newest&deals=1",
    );
  });

  it("toggles flags on and off", () => {
    expect(toggleFlagHref("/c/x", P(""), "verified")).toBe("/c/x?verified=1");
    expect(toggleFlagHref("/c/x", P("verified=1"), "verified")).toBe("/c/x");
  });

  it("uses endpoint-specific in-stock params", () => {
    expect(inStockHref("catalog", "/c/x", P(""))).toBe("/c/x?availability=in_stock");
    expect(inStockHref("catalog", "/c/x", P("availability=in_stock"))).toBe("/c/x");
    expect(inStockHref("search", "/s", P("q=a"))).toBe("/s?q=a&in_stock=1");
  });

  it("selects and unselects exact price bands", () => {
    expect(priceBandHref("/c/x", P(""), "500to2000")).toBe("/c/x?min_price=500&max_price=2000");
    expect(activePriceBand(P("min_price=500&max_price=2000"))).toBe("500to2000");
    expect(activePriceBand(P("min_price=501&max_price=2000"))).toBeNull();
    expect(priceBandHref("/c/x", P("min_price=500&max_price=2000"), "500to2000")).toBe("/c/x");
    expect(priceBandHref("/c/x", P("max_price=500"), "over5000")).toBe("/c/x?min_price=5000");
  });

  it("near me needs lat, lng and radius together", () => {
    expect(nearMeActive(P("lat=1&lng=2"))).toBe(false);
    expect(nearMeActive(P("lat=1&lng=2&radius_km=5"))).toBe(true);
    expect(nearMeOnHref("/c/x", P("sort=nearest"), { lat: -15.42, lng: 28.28 })).toBe(
      "/c/x?sort=nearest&lat=-15.42&lng=28.28&radius_km=5",
    );
    expect(nearMeOffHref("/c/x", P("lat=1&lng=2&radius_km=5&deals=1"))).toBe("/c/x?deals=1");
  });

  it("rating toggles and clear keeps only requested params", () => {
    expect(ratingHref("/c/x", P(""), "4")).toBe("/c/x?min_rating=4");
    expect(ratingHref("/c/x", P("min_rating=4"), "4")).toBe("/c/x");
    expect(clearFiltersHref("/c/x", P("sort=newest&deals=1&verified=1"), ["sort"])).toBe(
      "/c/x?sort=newest",
    );
  });
});
