import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { cookiesMock, createServerClientMock, absoluteApiUrlMock } = vi.hoisted(() => ({
  cookiesMock: vi.fn(),
  createServerClientMock: vi.fn(),
  absoluteApiUrlMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  cookies: cookiesMock,
}));

vi.mock("@vergeo/auth/server-client", () => ({
  createServerClient: createServerClientMock,
}));

vi.mock("../../../../../lib/api-base-url", () => ({
  absoluteApiUrl: absoluteApiUrlMock,
}));

import { isProductCartEmpty, readProductCartSnapshot } from "./server-product-cart";

describe("server-product-cart", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    cookiesMock.mockResolvedValue({
      getAll: () => [{ name: "vergeo_guest_cart", value: "token" }],
    });
    createServerClientMock.mockReturnValue({
      auth: {
        getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      },
    });
    absoluteApiUrlMock.mockReturnValue("https://api.test/cart");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("isProductCartEmpty is true only with zero lines", () => {
    expect(isProductCartEmpty({ itemCount: 0, ticketCount: 0 })).toBe(true);
    expect(isProductCartEmpty({ itemCount: 1, ticketCount: 0 })).toBe(false);
    expect(isProductCartEmpty({ itemCount: 0, ticketCount: 1 })).toBe(false);
  });

  it("readProductCartSnapshot counts product and ticket lines", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            items: [{ id: "a" }],
            ticket_lines: [{ id: "t" }],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(readProductCartSnapshot()).resolves.toEqual({
      itemCount: 1,
      ticketCount: 1,
    });
  });

  it("readProductCartSnapshot returns null when the API is unreachable", async () => {
    absoluteApiUrlMock.mockReturnValue(null);
    await expect(readProductCartSnapshot()).resolves.toBeNull();
  });
});
