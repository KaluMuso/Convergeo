import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./api-base-url", () => ({
  getApiBaseUrl: () => "https://api.example.test",
}));

vi.mock("@vergeo/auth/browser-client", () => ({
  createBrowserClient: () => ({
    auth: {
      getSession: async () => ({
        data: { session: { access_token: "token" } },
      }),
    },
  }),
}));

import { isFollowingVendor } from "./engagement-api";

describe("isFollowingVendor", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requests follows within API max page size", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ vendor_id: "v1" }] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await isFollowingVendor("v1");

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/me/follows?limit=50",
      expect.objectContaining({ method: "GET" }),
    );
  });
});
