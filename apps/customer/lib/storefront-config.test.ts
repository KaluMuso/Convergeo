import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  EMPTY_STOREFRONT_CONFIG,
  fetchStorefrontConfig,
  fetchStorefrontConfigClient,
  parseStorefrontConfig,
  resetStorefrontConfigCacheForTests,
} from "./storefront-config";

describe("parseStorefrontConfig", () => {
  it("accepts valid integers", () => {
    expect(
      parseStorefrontConfig({ free_delivery_threshold_ngwee: 35_000, low_stock_threshold: 3 }),
    ).toEqual({ freeDeliveryThresholdNgwee: 35_000, lowStockThreshold: 3 });
  });

  it("nulls missing, float, negative and zero-threshold values", () => {
    expect(parseStorefrontConfig({})).toEqual(EMPTY_STOREFRONT_CONFIG);
    expect(parseStorefrontConfig(null)).toEqual(EMPTY_STOREFRONT_CONFIG);
    expect(
      parseStorefrontConfig({ free_delivery_threshold_ngwee: 12.5, low_stock_threshold: -1 }),
    ).toEqual(EMPTY_STOREFRONT_CONFIG);
    expect(
      parseStorefrontConfig({ free_delivery_threshold_ngwee: 0 }).freeDeliveryThresholdNgwee,
    ).toBeNull();
  });
});

describe("storefront config fetch", () => {
  beforeEach(() => {
    resetStorefrontConfigCacheForTests();
    vi.stubEnv("NEXT_PUBLIC_DEPLOYMENT_PLANE", "development");
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("returns empty config when the API fails (server)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    expect(await fetchStorefrontConfig()).toEqual(EMPTY_STOREFRONT_CONFIG);
  });

  it("returns empty config on a non-OK response (client) and retries next time", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ free_delivery_threshold_ngwee: 20_000, low_stock_threshold: 5 }),
      });
    vi.stubGlobal("fetch", fetchMock);
    expect(await fetchStorefrontConfigClient()).toEqual(EMPTY_STOREFRONT_CONFIG);
    expect((await fetchStorefrontConfigClient()).freeDeliveryThresholdNgwee).toBe(20_000);
    expect(fetchMock.mock.calls[0]![0]).toBe("http://localhost:8000/public/config/storefront");
  });
});
