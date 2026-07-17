import { describe, expect, it } from "vitest";

import {
  bestActiveTier,
  isEarlyBirdActive,
  nextTierUpsell,
  resolveUnitPriceNgwee,
} from "./resolve-price";

import type { ResolvablePrice } from "./resolve-price";

const NOW = new Date("2026-07-01T00:00:00Z");
const BASE = 50_000;

function ticket(overrides: Partial<ResolvablePrice> = {}): ResolvablePrice {
  return {
    price_ngwee: BASE,
    early_bird_price_ngwee: null,
    early_bird_until: null,
    tiers: [],
    ...overrides,
  };
}

describe("resolveUnitPriceNgwee", () => {
  it("returns the base price with no discounts", () => {
    expect(resolveUnitPriceNgwee(ticket(), 1, NOW)).toBe(BASE);
  });

  it("applies early-bird strictly before the cutoff", () => {
    const t = ticket({
      early_bird_price_ngwee: 40_000,
      early_bird_until: "2026-07-02T00:00:00Z",
    });
    expect(resolveUnitPriceNgwee(t, 1, NOW)).toBe(40_000);
  });

  it("ignores early-bird at or after the cutoff", () => {
    const t = ticket({
      early_bird_price_ngwee: 40_000,
      early_bird_until: "2026-07-01T00:00:00Z", // exactly NOW → expired
    });
    expect(resolveUnitPriceNgwee(t, 1, NOW)).toBe(BASE);
    expect(isEarlyBirdActive(t, NOW)).toBe(false);
  });

  it("applies a group tier at and above its threshold, base below", () => {
    const t = ticket({ tiers: [{ min_qty: 5, price_ngwee: 44_000 }] });
    expect(resolveUnitPriceNgwee(t, 4, NOW)).toBe(BASE);
    expect(resolveUnitPriceNgwee(t, 5, NOW)).toBe(44_000);
    expect(resolveUnitPriceNgwee(t, 6, NOW)).toBe(44_000);
  });

  it("takes the lowest of early-bird and a qualifying tier", () => {
    const t = ticket({
      early_bird_price_ngwee: 45_000,
      early_bird_until: "2026-07-02T00:00:00Z",
      tiers: [{ min_qty: 3, price_ngwee: 42_000 }],
    });
    expect(resolveUnitPriceNgwee(t, 3, NOW)).toBe(42_000);
    expect(resolveUnitPriceNgwee(t, 1, NOW)).toBe(45_000);
  });

  it("never exceeds the base price", () => {
    const t = ticket({ tiers: [{ min_qty: 2, price_ngwee: 99_000 }] });
    expect(resolveUnitPriceNgwee(t, 5, NOW)).toBe(BASE);
  });
});

describe("bestActiveTier", () => {
  it("returns the lowest-priced qualifying tier, or null", () => {
    const t = ticket({
      tiers: [
        { min_qty: 2, price_ngwee: 46_000 },
        { min_qty: 5, price_ngwee: 42_000 },
      ],
    });
    expect(bestActiveTier(t, 1)).toBeNull();
    expect(bestActiveTier(t, 2)?.price_ngwee).toBe(46_000);
    expect(bestActiveTier(t, 5)?.price_ngwee).toBe(42_000);
  });
});

describe("nextTierUpsell", () => {
  it("returns null when there are no tiers", () => {
    expect(nextTierUpsell(ticket(), 1, NOW)).toBeNull();
  });

  it("points to the nearest higher tier that lowers the price", () => {
    const t = ticket({
      tiers: [
        { min_qty: 5, price_ngwee: 45_000 },
        { min_qty: 10, price_ngwee: 40_000 },
      ],
    });
    expect(nextTierUpsell(t, 1, NOW)).toEqual({ min_qty: 5, price_ngwee: 45_000 });
    // Once at 5, the next reachable saving is the 10+ tier.
    expect(nextTierUpsell(t, 5, NOW)).toEqual({ min_qty: 10, price_ngwee: 40_000 });
    // At/above the top tier there is nothing left to upsell.
    expect(nextTierUpsell(t, 10, NOW)).toBeNull();
  });

  it("ignores a higher tier that would not beat the current price", () => {
    // An active early-bird (39k) already beats the 5+ tier (45k) → no upsell.
    const t = ticket({
      early_bird_price_ngwee: 39_000,
      early_bird_until: "2026-08-01T00:00:00Z",
      tiers: [{ min_qty: 5, price_ngwee: 45_000 }],
    });
    expect(nextTierUpsell(t, 1, NOW)).toBeNull();
  });
});
