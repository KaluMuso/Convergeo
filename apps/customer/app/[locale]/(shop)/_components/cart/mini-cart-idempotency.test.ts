// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

import { addCartItem } from "./mini-cart-drawer";

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: vi.fn(async () => ({
    auth: { getSession: async () => ({ data: { session: null } }) },
  })),
}));
vi.mock("../../../../../lib/api-base-url", () => ({
  getApiBaseUrl: () => "http://localhost:8000",
}));

const cart = {
  cart_id: "cart-1",
  items: [],
  vendor_groups: [],
  subtotal_ngwee: 0,
  conflicts: [],
  notices: [],
};

beforeEach(() => {
  sessionStorage.clear();
  vi.stubGlobal("crypto", {
    randomUUID: vi
      .fn()
      .mockReturnValueOnce("key-1")
      .mockReturnValueOnce("key-2")
      .mockReturnValueOnce("key-3"),
  });
});

describe("cart add retry keys", () => {
  it("reuses a key after an interrupted request and rotates it after success", async () => {
    const keys: string[] = [];
    let attempts = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith("/cart/items")) {
          keys.push(new Headers(init?.headers).get("Idempotency-Key") ?? "");
          if (++attempts === 1) throw new Error("connection lost after send");
        }
        return Response.json(cart);
      }),
    );

    await expect(addCartItem("listing-1", 2)).rejects.toThrow();
    expect(sessionStorage.length).toBe(1);
    await addCartItem("listing-1", 2);
    await addCartItem("listing-1", 2);
    expect(keys).toEqual(["key-1", "key-1", "key-2"]);
    expect(sessionStorage.length).toBe(0);
  });

  it("uses a fresh key after a definitive validation failure", async () => {
    const keys: string[] = [];
    let attempts = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith("/cart/items")) {
          keys.push(new Headers(init?.headers).get("Idempotency-Key") ?? "");
          if (++attempts === 1) {
            return Response.json(
              { error: { code: "cart.out_of_stock", message: "Unavailable" } },
              { status: 422 },
            );
          }
        }
        return Response.json(cart);
      }),
    );

    await expect(addCartItem("listing-1", 2)).rejects.toThrow();
    await addCartItem("listing-1", 2);
    expect(keys).toEqual(["key-1", "key-2"]);
  });

  it("gives overlapping intentional adds distinct keys", async () => {
    const keys: string[] = [];
    let completeFirst: ((response: Response) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith("/cart/items")) {
          keys.push(new Headers(init?.headers).get("Idempotency-Key") ?? "");
          if (keys.length === 1) {
            return new Promise<Response>((resolve) => {
              completeFirst = resolve;
            });
          }
        }
        return Response.json(cart);
      }),
    );

    const first = addCartItem("listing-1", 2);
    const second = addCartItem("listing-1", 2);
    await vi.waitFor(() => expect(keys).toHaveLength(2));
    expect(keys).toEqual(["key-1", "key-2"]);
    completeFirst?.(Response.json(cart));
    await Promise.all([first, second]);
  });
});
