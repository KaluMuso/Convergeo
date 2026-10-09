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

  it("retains the key after validation failure until a retry confirms the outcome", async () => {
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
    await addCartItem("listing-1", 2);
    expect(keys).toEqual(["key-1", "key-1", "key-2"]);
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

  it("retains the first key when its response is lost after the second add succeeds", async () => {
    const keys: string[] = [];
    let loseFirst: ((error: Error) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith("/cart/items")) {
          keys.push(new Headers(init?.headers).get("Idempotency-Key") ?? "");
          if (keys.length === 1) {
            return new Promise<Response>((_resolve, reject) => {
              loseFirst = reject;
            });
          }
        }
        return Response.json(cart);
      }),
    );

    const first = addCartItem("listing-1", 2);
    const firstOutcome = first.catch((error: unknown) => error);
    const second = addCartItem("listing-1", 2);
    await vi.waitFor(() => expect(keys).toHaveLength(2));
    await second;
    loseFirst?.(new Error("response lost after server commit"));
    expect(await firstOutcome).toBeInstanceOf(Error);
    expect(sessionStorage.length).toBe(1);
    await addCartItem("listing-1", 2);
    await addCartItem("listing-1", 2);
    expect(keys).toEqual(["key-1", "key-2", "key-1", "key-3"]);
  });

  it("retains the second key when its response is lost after the first add succeeds", async () => {
    const keys: string[] = [];
    let loseSecond: ((error: Error) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith("/cart/items")) {
          keys.push(new Headers(init?.headers).get("Idempotency-Key") ?? "");
          if (keys.length === 2) {
            return new Promise<Response>((_resolve, reject) => {
              loseSecond = reject;
            });
          }
        }
        return Response.json(cart);
      }),
    );

    const first = addCartItem("listing-1", 2);
    const second = addCartItem("listing-1", 2);
    const secondOutcome = second.catch((error: unknown) => error);
    await vi.waitFor(() => expect(keys).toHaveLength(2));
    await first;
    loseSecond?.(new Error("response lost after server commit"));
    expect(await secondOutcome).toBeInstanceOf(Error);
    expect(sessionStorage.length).toBe(1);
    await addCartItem("listing-1", 2);
    await addCartItem("listing-1", 2);
    expect(keys).toEqual(["key-1", "key-2", "key-2", "key-3"]);
  });

  it("recovers an unresolved key after a page-module reload", async () => {
    const keys: string[] = [];
    let attempts = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith("/cart/items")) {
          keys.push(new Headers(init?.headers).get("Idempotency-Key") ?? "");
          if (++attempts === 1)
            throw new Error("navigation interrupted response");
        }
        return Response.json(cart);
      }),
    );

    await expect(addCartItem("listing-1", 2)).rejects.toThrow();
    vi.resetModules();
    const reloaded = await import("./mini-cart-drawer");
    await reloaded.addCartItem("listing-1", 2);
    await reloaded.addCartItem("listing-1", 2);
    expect(keys).toEqual(["key-1", "key-1", "key-2"]);
  });
});
