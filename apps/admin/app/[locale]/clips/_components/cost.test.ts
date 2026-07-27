import { describe, expect, it } from "vitest";

import { formatUsdMicros, spendPercent } from "./cost";

/**
 * M17-P08 — cost display.
 *
 * Money arrives as integer micro-USD; the division happens here and nowhere
 * else. These tests exist because two screens formatting the same number two
 * different ways is how an operator loses confidence in the dashboard right
 * when they most need to trust it.
 */

describe("formatUsdMicros", () => {
  it("renders whole and fractional dollars to two places", () => {
    expect(formatUsdMicros(1_000_000)).toBe("$1.00");
    expect(formatUsdMicros(1_500_000)).toBe("$1.50");
    expect(formatUsdMicros(20_000)).toBe("$0.02");
  });

  it("treats absent or nonsense values as zero rather than NaN", () => {
    expect(formatUsdMicros(0)).toBe("$0.00");
    expect(formatUsdMicros(Number.NaN)).toBe("$0.00");
    expect(formatUsdMicros(-1)).toBe("$0.00");
  });
});

describe("spendPercent", () => {
  it("reports the share of the cap consumed", () => {
    expect(spendPercent(2_500_000, 10_000_000)).toBe(25);
    expect(spendPercent(10_000_000, 10_000_000)).toBe(100);
  });

  it("clamps above the cap rather than reporting 140%", () => {
    expect(spendPercent(14_000_000, 10_000_000)).toBe(100);
  });

  it("treats a zero cap as unbounded, matching the API convention", () => {
    expect(spendPercent(5_000_000, 0)).toBe(0);
  });
});
