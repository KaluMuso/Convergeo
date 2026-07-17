import { describe, expect, it } from "vitest";

import {
  isoToLocalDateTime,
  localDateTimeToIso,
  pricingErrorKey,
  resolveEarlyBird,
  resolveTiers,
  type TierDraft,
} from "./pricing";

const BASE = 7500; // K75.00 base price, in ngwee
const NOW = new Date("2026-07-17T00:00:00Z");
const FUTURE = "2027-01-01T09:00";
const PAST = "2020-01-01T09:00";

describe("resolveEarlyBird", () => {
  it("clears when both fields are blank", () => {
    const res = resolveEarlyBird({ priceZmw: "", untilLocal: "" }, BASE, NOW);
    expect(res).toEqual({
      ok: true,
      input: { early_bird_price_ngwee: null, early_bird_until: null },
    });
  });

  it("rejects an incomplete pair", () => {
    expect(resolveEarlyBird({ priceZmw: "60.00", untilLocal: "" }, BASE, NOW)).toEqual({
      ok: false,
      errorKey: "errors.earlyBirdIncomplete",
    });
    expect(resolveEarlyBird({ priceZmw: "", untilLocal: FUTURE }, BASE, NOW)).toEqual({
      ok: false,
      errorKey: "errors.earlyBirdIncomplete",
    });
  });

  it("rejects a price at or above the base (not a discount)", () => {
    expect(resolveEarlyBird({ priceZmw: "75.00", untilLocal: FUTURE }, BASE, NOW)).toEqual({
      ok: false,
      errorKey: "errors.notDiscount",
    });
  });

  it("rejects a cutoff in the past", () => {
    expect(resolveEarlyBird({ priceZmw: "60.00", untilLocal: PAST }, BASE, NOW)).toEqual({
      ok: false,
      errorKey: "errors.pastCutoff",
    });
  });

  it("rejects an invalid price", () => {
    expect(resolveEarlyBird({ priceZmw: "abc", untilLocal: FUTURE }, BASE, NOW).ok).toBe(false);
  });

  it("accepts a valid early-bird below base with a future cutoff", () => {
    const res = resolveEarlyBird({ priceZmw: "60.00", untilLocal: FUTURE }, BASE, NOW);
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.input.early_bird_price_ngwee).toBe(6000);
      expect(res.input.early_bird_until).toBe(localDateTimeToIso(FUTURE));
    }
  });
});

describe("resolveTiers", () => {
  it("drops fully-blank rows (removal) and returns empty", () => {
    const rows: TierDraft[] = [{ minQty: "", priceZmw: "" }];
    expect(resolveTiers(rows, BASE)).toEqual({ ok: true, tiers: [] });
  });

  it("resolves and sorts valid tiers", () => {
    const rows: TierDraft[] = [
      { minQty: "10", priceZmw: "55.00" },
      { minQty: "5", priceZmw: "65.00" },
    ];
    expect(resolveTiers(rows, BASE)).toEqual({
      ok: true,
      tiers: [
        { min_qty: 5, price_ngwee: 6500 },
        { min_qty: 10, price_ngwee: 5500 },
      ],
    });
  });

  it("rejects min_qty below 2 or non-integer", () => {
    expect(resolveTiers([{ minQty: "1", priceZmw: "60.00" }], BASE).ok).toBe(false);
    expect(resolveTiers([{ minQty: "2.5", priceZmw: "60.00" }], BASE)).toEqual({
      ok: false,
      errorKey: "errors.minQtyInvalid",
    });
  });

  it("rejects duplicate min_qty", () => {
    const rows: TierDraft[] = [
      { minQty: "5", priceZmw: "65.00" },
      { minQty: "5", priceZmw: "64.00" },
    ];
    expect(resolveTiers(rows, BASE)).toEqual({ ok: false, errorKey: "errors.duplicateMinQty" });
  });

  it("rejects a tier price at or above the base", () => {
    expect(resolveTiers([{ minQty: "5", priceZmw: "75.00" }], BASE)).toEqual({
      ok: false,
      errorKey: "errors.tierNotDiscount",
    });
  });
});

describe("pricingErrorKey", () => {
  it("maps known server codes and falls back to saveFailed", () => {
    expect(pricingErrorKey("early_bird_not_a_discount")).toBe("errors.notDiscount");
    expect(pricingErrorKey("early_bird_cutoff_in_past")).toBe("errors.pastCutoff");
    expect(pricingErrorKey("tier_not_a_discount")).toBe("errors.tierNotDiscount");
    expect(pricingErrorKey("pricing_not_allowed_on_free")).toBe("errors.onFree");
    expect(pricingErrorKey("something_else")).toBe("errors.saveFailed");
    expect(pricingErrorKey(undefined)).toBe("errors.saveFailed");
  });
});

describe("datetime round-trip", () => {
  it("isoToLocalDateTime inverts localDateTimeToIso", () => {
    const iso = localDateTimeToIso(FUTURE);
    expect(iso).not.toBeNull();
    expect(isoToLocalDateTime(iso)).toBe(FUTURE);
  });

  it("returns empty/null on blanks", () => {
    expect(localDateTimeToIso("")).toBeNull();
    expect(isoToLocalDateTime(null)).toBe("");
  });
});
