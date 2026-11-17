import { afterEach, describe, expect, it, vi } from "vitest";

import { dealToListing, fetchDeals, type DealItem } from "./deals-data";

const deal: DealItem = {
  deal_id: "d1",
  starts_at: "2026-01-01T00:00:00Z",
  ends_at: "2026-01-02T00:00:00Z",
  deal_price_ngwee: 7500,
  reference_price_ngwee: 10000,
  discount_percent: 25,
  listing: {
    id: "l1",
    title: "Chitenge",
    product_slug: "chitenge",
    vendor_name: "Kabwata",
    price_ngwee: 10000,
    condition: "new",
    in_stock: true,
    image_public_id: "x/y",
    rating: 4,
    review_count: 3,
    distance_m: null,
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("dealToListing", () => {
  it("uses the deal price as live price and the reference price as the struck original", () => {
    const listing = dealToListing(deal);
    expect(listing.priceNgwee).toBe(7500);
    expect(listing.oldNgwee).toBe(10000);
    expect(listing.deliveryAvailable).toBe(false);
  });
});

describe("fetchDeals", () => {
  it("resolves null (rail hidden) when the API is unreachable", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.example.test");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    await expect(fetchDeals(12)).resolves.toBeNull();
  });

  it("resolves null on a non-OK response", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.example.test");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
    await expect(fetchDeals(12)).resolves.toBeNull();
  });
});
