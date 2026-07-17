import { describe, expect, it } from "vitest";

import { isEarlyBirdActive, nextTier, resolveUnitPriceNgwee, type DisplayPricing } from "./pricing";

const NOW = new Date("2026-07-17T00:00:00Z");
const FUTURE = "2026-08-01T00:00:00Z";
const PAST = "2026-07-01T00:00:00Z";

function pricing(overrides: Partial<DisplayPricing> = {}): DisplayPricing {
  return {
    price_ngwee: 50_000,
    early_bird_price_ngwee: null,
    early_bird_until: null,
    tiers: [],
    ...overrides,
  };
}

describe("resolveUnitPriceNgwee", () => {
  it("returns the base price with no discounts", () => {
    expect(resolveUnitPriceNgwee(pricing(), 1, NOW)).toBe(50_000);
  });

  it("applies an active early-bird price", () => {
    const p = pricing({ early_bird_price_ngwee: 40_000, early_bird_until: FUTURE });
    expect(resolveUnitPriceNgwee(p, 1, NOW)).toBe(40_000);
  });

  it("ignores an expired early-bird price", () => {
    const p = pricing({ early_bird_price_ngwee: 40_000, early_bird_until: PAST });
    expect(resolveUnitPriceNgwee(p, 1, NOW)).toBe(50_000);
  });

  it("applies a qualifying group tier and ignores one below threshold", () => {
    const p = pricing({ tiers: [{ min_qty: 5, price_ngwee: 45_000 }] });
    expect(resolveUnitPriceNgwee(p, 5, NOW)).toBe(45_000);
    expect(resolveUnitPriceNgwee(p, 4, NOW)).toBe(50_000);
  });

  it("takes the lowest of active early-bird and a qualifying tier", () => {
    const p = pricing({
      early_bird_price_ngwee: 42_000,
      early_bird_until: FUTURE,
      tiers: [{ min_qty: 10, price_ngwee: 40_000 }],
    });
    expect(resolveUnitPriceNgwee(p, 10, NOW)).toBe(40_000); // tier < early-bird
    expect(resolveUnitPriceNgwee(p, 5, NOW)).toBe(42_000); // tier not reached
  });

  it("never exceeds the base price for a misconfigured higher discount", () => {
    const p = pricing({ tiers: [{ min_qty: 2, price_ngwee: 99_000 }] });
    expect(resolveUnitPriceNgwee(p, 5, NOW)).toBe(50_000);
  });
});

describe("isEarlyBirdActive", () => {
  it("is true before the cutoff and false at/after it", () => {
    expect(
      isEarlyBirdActive(pricing({ early_bird_price_ngwee: 1, early_bird_until: FUTURE }), NOW),
    ).toBe(true);
    expect(
      isEarlyBirdActive(pricing({ early_bird_price_ngwee: 1, early_bird_until: PAST }), NOW),
    ).toBe(false);
    expect(isEarlyBirdActive(pricing(), NOW)).toBe(false);
  });
});

describe("nextTier", () => {
  it("returns the nearest not-yet-reached tier, or null", () => {
    const p = pricing({
      tiers: [
        { min_qty: 5, price_ngwee: 45_000 },
        { min_qty: 10, price_ngwee: 40_000 },
      ],
    });
    expect(nextTier(p, 1)).toEqual({ min_qty: 5, price_ngwee: 45_000 });
    expect(nextTier(p, 5)).toEqual({ min_qty: 10, price_ngwee: 40_000 });
    expect(nextTier(p, 10)).toBeNull();
  });
});
