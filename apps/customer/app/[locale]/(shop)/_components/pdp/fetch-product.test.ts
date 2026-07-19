import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../../../lib/api-base-url", () => ({
  absoluteApiUrl: (path: string) =>
    path.startsWith("http") ? path : `https://api.example.test${path}`,
  getApiBaseUrl: () => "https://api.example.test",
}));

vi.mock("@vergeo/config", () => ({
  createApiClient: () => ({
    request: vi.fn(),
  }),
}));

import { fetchProduct } from "./fetch-product";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("fetchProduct", () => {
  it("returns product data for a resolved slug", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 200,
        ok: true,
        headers: new Headers(),
        json: async () => ({
          id: "p1",
          name: "Itel A70 Smartphone",
          slug: "itel-a70",
          brand: "Itel",
          description: null,
          spec: {},
          category_id: "c1",
          images: [],
          listings: [],
          listing_count: 0,
        }),
      }),
    );

    const result = await fetchProduct("itel-a70");
    expect(result).toEqual({
      kind: "product",
      data: expect.objectContaining({ slug: "itel-a70", name: "Itel A70 Smartphone" }),
    });
    expect(fetch).toHaveBeenCalledWith(
      "https://api.example.test/products/itel-a70",
      expect.objectContaining({ redirect: "manual" }),
    );
  });

  it("maps API 404 to not_found (genuine missing product)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 404,
        ok: false,
        headers: new Headers(),
        json: async () => ({ error: { code: "product.not_found" } }),
      }),
    );

    await expect(fetchProduct("does-not-exist")).resolves.toEqual({ kind: "not_found" });
  });

  it("maps API 5xx / network-class failures to unavailable (not a soft-404)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 500,
        ok: false,
        headers: new Headers(),
        json: async () => ({ error: { code: "internal_error" } }),
      }),
    );

    await expect(fetchProduct("itel-a70")).resolves.toEqual({ kind: "unavailable" });
  });

  it("follows API slug redirect for UUID / merged identities", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 301,
        ok: false,
        headers: new Headers({ location: "/products/itel-a70" }),
        json: async () => ({}),
      }),
    );

    await expect(fetchProduct("a0000133-0000-4000-8000-000000000001")).resolves.toEqual({
      kind: "redirect",
      slug: "itel-a70",
    });
  });
});
