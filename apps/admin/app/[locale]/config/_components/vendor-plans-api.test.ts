import { describe, expect, it } from "vitest";

import {
  EMPTY_DRAFT,
  draftToPayload,
  isValidPlanKey,
  overrideToPayload,
  planPatch,
  planToDraft,
  type VendorPlan,
} from "./vendor-plans-api";

const STARTER: VendorPlan = {
  key: "starter",
  name: "Starter",
  price_ngwee: 4900,
  max_listings: 150,
  max_images_per_listing: 8,
  featured_slots: 1,
  analytics_depth: "standard",
  wholesale_tools: false,
  is_default: false,
  active: true,
  position: 1,
  vendor_count: 3,
};

describe("draftToPayload", () => {
  it("converts kwacha to integer ngwee without float drift", () => {
    const result = draftToPayload({ ...EMPTY_DRAFT, name: "Stall", price: "49.99" });
    expect(result).toMatchObject({ ok: true, payload: { price_ngwee: 4999 } });
    const k = draftToPayload({ ...EMPTY_DRAFT, name: "Stall", price: "K1,234.5" });
    expect(k).toMatchObject({ ok: true, payload: { price_ngwee: 123450 } });
  });

  it("treats an empty listing limit as unlimited (null)", () => {
    const result = draftToPayload({ ...EMPTY_DRAFT, name: "Pro", maxListings: "" });
    expect(result).toMatchObject({ ok: true, payload: { max_listings: null } });
  });

  it.each([
    [{ name: " " }, "nameRequired"],
    [{ price: "-1" }, "priceInvalid"],
    [{ price: "49.999" }, "priceInvalid"],
    [{ price: "abc" }, "priceInvalid"],
    [{ maxListings: "2.5" }, "listingsInvalid"],
    [{ maxListings: "-3" }, "listingsInvalid"],
    [{ maxImages: "9" }, "imagesInvalid"],
    [{ maxImages: "0" }, "imagesInvalid"],
    [{ featuredSlots: "101" }, "slotsInvalid"],
  ])("rejects %o with %s", (patch, error) => {
    expect(draftToPayload({ ...EMPTY_DRAFT, name: "Plan", ...patch })).toEqual({
      ok: false,
      error,
    });
  });
});

describe("planPatch", () => {
  it("sends only changed fields and keeps null for unlimited", () => {
    const draft = { ...planToDraft(STARTER), price: "59", maxListings: "" };
    const result = draftToPayload(draft);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(planPatch(STARTER, result.payload)).toEqual({
      price_ngwee: 5900,
      max_listings: null,
    });
  });

  it("is empty when nothing changed", () => {
    const result = draftToPayload(planToDraft(STARTER));
    expect(result.ok && planPatch(STARTER, result.payload)).toEqual({});
  });
});

describe("isValidPlanKey", () => {
  it.each([
    ["market_stall", true],
    ["pro2", true],
    ["Pro", false],
    ["2pro", false],
    ["a", false],
    ["has space", false],
  ])("%s -> %s", (key, ok) => {
    expect(isValidPlanKey(key)).toBe(ok);
  });
});

describe("overrideToPayload", () => {
  const now = new Date(2026, 10, 13, 12, 0, 0);
  const base = {
    unlimited: false,
    maxListings: "",
    maxImages: "",
    expiresOn: "2026-12-31",
    reason: "Promo",
  };

  it("builds an unlimited override expiring at the end of the chosen day", () => {
    const result = overrideToPayload({ ...base, unlimited: true, maxListings: "40" }, now);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.payload.unlimited_listings).toBe(true);
    expect(result.payload.max_listings).toBeNull();
    expect(new Date(result.payload.expires_at).getHours()).toBe(23);
    expect(result.payload.expires_at.endsWith("Z")).toBe(true);
  });

  it.each([
    [{}, "overrideEmpty"],
    [{ maxListings: "x" }, "listingsInvalid"],
    [{ maxImages: "12" }, "imagesInvalid"],
    [{ maxListings: "10", expiresOn: "2026-11-01" }, "expiryInvalid"],
    [{ maxListings: "10", expiresOn: "" }, "expiryInvalid"],
    [{ maxListings: "10", reason: "  " }, "reasonRequired"],
  ])("rejects %o with %s", (patch, error) => {
    expect(overrideToPayload({ ...base, ...patch }, now)).toEqual({ ok: false, error });
  });
});
