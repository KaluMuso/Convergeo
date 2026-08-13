import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../../../lib/api-base-url", () => ({
  absoluteApiUrl: (path: string) => `https://api.example.test${path}`,
}));

import { fetchStandaloneListing } from "./fetch-listing";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("fetchStandaloneListing", () => {
  it("loads the public standalone-listing contract by encoded id", async () => {
    const listing = {
      id: "listing/id",
      title: "Measured timber",
      product_class: "C",
      condition: "new",
      defect_notes: null,
      price_ngwee: 25_000,
      compare_at_ngwee: null,
      sale_unit: "metre",
      unit_step_milli: 500,
      min_steps: 2,
      fulfilment_mode: "stocked",
      lead_time_days: null,
      vendor_capacity_per_week: null,
      stock_mode: "tracked",
      stock_qty: 20,
      in_stock: true,
      moq: 1,
      wholesale: false,
      vendor: { id: "vendor-1", name: "Timber House", slug: "timber-house" },
      location: null,
      images: [],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => listing }),
    );

    await expect(fetchStandaloneListing("listing/id")).resolves.toEqual({
      kind: "listing",
      data: listing,
    });
    expect(fetch).toHaveBeenCalledWith(
      "https://api.example.test/catalog/listings/listing%2Fid",
      expect.objectContaining({
        next: expect.objectContaining({ tags: ["listing:listing/id", "catalog-listings"] }),
      }),
    );
  });

  it("keeps confirmed missing listings distinct from transient failures", async () => {
    const request = vi.fn();
    vi.stubGlobal("fetch", request.mockResolvedValueOnce({ status: 404, ok: false }));
    await expect(fetchStandaloneListing("missing")).resolves.toEqual({ kind: "not_found" });

    request.mockResolvedValueOnce({ status: 503, ok: false });
    await expect(fetchStandaloneListing("temporarily-down")).resolves.toEqual({
      kind: "unavailable",
    });
  });

  it("forwards business identity without sharing the response cache", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 404, ok: false }));

    await fetchStandaloneListing("wholesale-listing", "business-token");

    expect(fetch).toHaveBeenCalledWith(
      "https://api.example.test/catalog/listings/wholesale-listing",
      {
        headers: { Authorization: "Bearer business-token" },
        cache: "no-store",
      },
    );
  });
});
