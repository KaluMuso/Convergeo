import { describe, expect, it } from "vitest";

import { formatSaleQuantity } from "./quantity";

describe("formatSaleQuantity", () => {
  it("formats whole and fractional sale steps exactly", () => {
    expect(formatSaleQuantity(3, 1_000, "en")).toBe("3");
    expect(formatSaleQuantity(3, 250, "en")).toBe("0.75");
    expect(formatSaleQuantity(3, 500, "en")).toBe("1.5");
  });

  it("uses the locale decimal and grouping separators", () => {
    expect(formatSaleQuantity(2_001, 500, "en")).toBe("1,000.5");
    expect(formatSaleQuantity(2_001, 500, "fr")).toBe("1\u202f000,5");
  });

  it("rejects unsafe or non-integer storage values", () => {
    expect(() => formatSaleQuantity(1.5, 1_000)).toThrow(RangeError);
    expect(() => formatSaleQuantity(1, 0)).toThrow(RangeError);
    expect(() => formatSaleQuantity(Number.MAX_SAFE_INTEGER, 2)).toThrow(RangeError);
  });
});
