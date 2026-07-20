import { describe, expect, it } from "vitest";

import { buildOfferPriceContext } from "./offer-price-context";

describe("buildOfferPriceContext", () => {
  it("returns null for one seller", () => {
    expect(buildOfferPriceContext(100_000, [100_000])).toBeNull();
  });

  it("labels the cheapest selected offer", () => {
    expect(buildOfferPriceContext(90_000, [90_000, 120_000])).toEqual({ kind: "lowest" });
  });

  it("returns a real ngwee delta when the selected offer is higher", () => {
    expect(buildOfferPriceContext(120_000, [90_000, 120_000])).toEqual({
      kind: "more",
      diffNgwee: 30_000,
    });
  });
});
