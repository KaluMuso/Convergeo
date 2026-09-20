import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./api-base-url", () => ({
  getApiBaseUrl: () => "https://api.example.com",
}));

import { mergeGuestCartIntoAccount } from "./cart-merge";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("mergeGuestCartIntoAccount", () => {
  it("posts the real bearer token and HttpOnly guest cookie to the cart merge endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ id: "account-cart" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await mergeGuestCartIntoAccount("real-session-token");

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://api.example.com/cart/merge");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer real-session-token");
    expect(init.body).toBeUndefined();
  });
});
