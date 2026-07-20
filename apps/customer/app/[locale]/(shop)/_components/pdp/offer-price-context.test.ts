import { describe, expect, it } from "vitest";

import { buildOfferPriceContext } from "./offer-price-context";

const labels = {
  lowestPrice: "Lowest price among sellers",
  moreThanLowest: "{diff} more than the lowest offer",
};

describe("buildOfferPriceContext", () => {
  it("returns null for one seller", () => {
    expect(buildOfferPriceContext(100_000, [100_000], labels)).toBeNull();
  });

  it("labels the cheapest selected offer", () => {
    expect(buildOfferPriceContext(90_000, [90_000, 120_000], labels)).toBe(
      "Lowest price among sellers",
    );
  });

  it("shows a real delta when the selected offer is higher", () => {
    const result = buildOfferPriceContext(120_000, [90_000, 120_000], labels);
    expect(result).toContain("more than the lowest offer");
    expect(result).not.toContain("{diff}");
  });
});
