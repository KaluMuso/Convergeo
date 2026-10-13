// @vitest-environment jsdom
import { webcrypto } from "node:crypto";

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";
import { syncWishlistWithServer } from "../../../../../lib/engagement-api";
import { upsertWishlistLocal } from "../../../../../lib/wishlist-local";

import {
  addCartItem,
  refreshCart,
  resetCartClientForTests,
  saveCartItemForLater,
  setStoreStateForTests,
  useCartStore,
} from "./mini-cart-drawer";

const authState = vi.hoisted(() => ({
  session: null as null | { access_token: string; user: { id: string } },
  error: null as null | { message: string },
  beforeRead: null as null | (() => void),
  snapshotRead: null as null | (() => Promise<{ data: { session: null }; error: null }>),
}));

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: vi.fn(async () => ({
    auth: {
      getSession: async () => {
        if (authState.snapshotRead) return authState.snapshotRead();
        authState.beforeRead?.();
        return { data: { session: authState.session }, error: authState.error };
      },
    },
  })),
}));
vi.mock("../../../../../lib/api-base-url", () => ({
  getApiBaseUrl: vi.fn(() => "http://localhost:8000"),
}));

vi.mock("../../../../../lib/wishlist-local", () => ({ upsertWishlistLocal: vi.fn() }));
vi.mock("../../../../../lib/engagement-api", () => ({ syncWishlistWithServer: vi.fn() }));

const cart = {
  cart_id: "cart-1",
  items: [],
  vendor_groups: [],
  subtotal_ngwee: 0,
  conflicts: [],
  notices: [],
};

beforeEach(() => {
  vi.mocked(upsertWishlistLocal).mockClear();
  vi.mocked(syncWishlistWithServer).mockClear();
  authState.session = null;
  authState.error = null;
  authState.beforeRead = null;
  authState.snapshotRead = null;
  sessionStorage.clear();
  resetCartClientForTests();
  setStoreStateForTests({
    cart: null,
    notices: [],
    loading: false,
    loadError: false,
  });
  vi.mocked(getApiBaseUrl).mockReturnValue("http://localhost:8000");
  let generated = 0;
  vi.stubGlobal("crypto", {
    randomUUID: vi.fn(() => `key-${++generated}`),
    subtle: webcrypto.subtle,
  });
});

afterEach(async () => {
  // Let already-settled reconciliation reads finish before restoring mocks.
  await new Promise((resolve) => setTimeout(resolve, 10));
  resetCartClientForTests();
  cleanup();
  vi.unstubAllGlobals();
});

function session(userId: string, sessionId: string, revision = 1) {
  const payload = btoa(JSON.stringify({ sub: userId, session_id: sessionId, revision }));
  return {
    access_token: `synthetic.${payload}.not-a-real-signature`,
    user: { id: userId },
  };
}

function postedKeys(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls
    .filter(([url, init]) => String(url).endsWith("/cart/items") && init?.method === "POST")
    .map(([, init]) => new Headers(init?.headers).get("Idempotency-Key"));
}

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
          if (++attempts === 1) throw new Error("navigation interrupted response");
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

describe("session-bound confirmation and retry contract", () => {
  it.each<[string, () => Response]>([
    ["null", () => Response.json(null)],
    ["missing cart fields", () => Response.json({})],
    ["HTML", () => new Response("<html>not a cart</html>", { status: 200 })],
    [
      "invalid JSON",
      () =>
        new Response("{broken", {
          headers: { "Content-Type": "application/json" },
        }),
    ],
    ["invalid ngwee", () => Response.json({ ...cart, subtotal_ngwee: "0" })],
    ["malformed notices", () => Response.json({ ...cart, notices: [{}] })],
    [
      "coercible notice kind",
      () =>
        Response.json({
          ...cart,
          notices: [
            {
              listing_id: "l",
              kind: ["price_changed"],
              requested_qty: 1,
              available_qty: 1,
              snapshot_price_ngwee: 100,
              current_price_ngwee: 200,
            },
          ],
        }),
    ],
    [
      "malformed vendor name",
      () =>
        Response.json({
          ...cart,
          vendor_groups: [
            {
              vendor_id: "v",
              vendor_name: {},
              items: [],
              subtotal_ngwee: 0,
              delivery_eligible: false,
            },
          ],
        }),
    ],
    ...[
      "sale_unit",
      "unit_step_milli",
      "min_steps",
      "fulfilment_mode",
      "lead_time_days",
      "is_rfq_quote",
    ].map(
      (field) =>
        [
          field,
          () =>
            Response.json({
              ...cart,
              items: [
                {
                  id: "i",
                  listing_id: "l",
                  vendor_id: "v",
                  qty: 1,
                  unit_price_ngwee: 0,
                  line_total_ngwee: 0,
                  wholesale: false,
                  title_override: null,
                  [field]: {},
                },
              ],
            }),
        ] as [string, () => Response],
    ),
  ])("retains the key after malformed 2xx: %s", async (_name, invalid) => {
    let attempts = 0;
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url.endsWith("/cart/items") && ++attempts === 1) return invalid();
      return Response.json(cart);
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(addCartItem("listing-1", 2)).rejects.toThrow();
    expect(sessionStorage.length).toBe(1);
    await addCartItem("listing-1", 2);
    await addCartItem("listing-1", 2);
    expect(postedKeys(fetchMock)).toEqual(["key-1", "key-1", "key-2"]);
  });

  it("does not reserve keys or fetch when API origin is missing", async () => {
    vi.mocked(getApiBaseUrl).mockReturnValue("");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(addCartItem("listing-1", 2)).rejects.toThrow("API unavailable");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(sessionStorage.length).toBe(0);
  });

  it("keeps a retry key across access-token refresh within the same session", async () => {
    const first = session("user-a", "session-a", 1);
    const refreshed = session("user-a", "session-a", 2);
    authState.session = first;
    let attempts = 0;
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url.endsWith("/cart/items") && ++attempts === 1) throw new Error("lost response");
      return Response.json(cart);
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(addCartItem("listing-1", 2)).rejects.toThrow();
    authState.session = refreshed;
    await addCartItem("listing-1", 2);
    expect(postedKeys(fetchMock)).toEqual(["key-1", "key-1"]);
    const posts = fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/cart/items"));
    expect(new Headers(posts[0]?.[1]?.headers).get("Authorization")).toBe(
      `Bearer ${first.access_token}`,
    );
    expect(new Headers(posts[1]?.[1]?.headers).get("Authorization")).toBe(
      `Bearer ${refreshed.access_token}`,
    );
    for (let index = 0; index < sessionStorage.length; index++) {
      expect(sessionStorage.key(index)).not.toContain(first.access_token);
      expect(sessionStorage.getItem(sessionStorage.key(index)!)).not.toContain(first.access_token);
    }
  });

  it.each([
    ["different account", "user-b", "session-b"],
    ["new session for same account", "user-a", "session-b"],
  ])("allocates a fresh key for %s", async (_name, userId, sessionId) => {
    authState.session = session("user-a", "session-a");
    let attempts = 0;
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url.endsWith("/cart/items") && ++attempts === 1) throw new Error("lost response");
      return Response.json(cart);
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(addCartItem("listing-1", 2)).rejects.toThrow();
    const next = session(userId, sessionId);
    authState.session = next;
    await addCartItem("listing-1", 2);
    expect(postedKeys(fetchMock)).toEqual(["key-1", "key-2"]);
    const last = [...fetchMock.mock.calls]
      .reverse()
      .find(([url]) => String(url).endsWith("/cart/items"));
    expect(new Headers(last?.[1]?.headers).get("Authorization")).toBe(
      `Bearer ${next.access_token}`,
    );
  });

  it("refuses sending an old-session key with a new-account Authorization", async () => {
    authState.session = session("user-a", "session-a");
    let reads = 0;
    authState.beforeRead = () => {
      if (++reads === 2) authState.session = session("user-b", "session-b");
    };
    const fetchMock = vi.fn(async () => Response.json(cart));
    vi.stubGlobal("fetch", fetchMock);
    await expect(addCartItem("listing-1", 2)).rejects.toMatchObject({
      code: "cart.session_changed",
    });
    expect(fetchMock).not.toHaveBeenCalled();
    authState.beforeRead = null;
    await addCartItem("listing-1", 2);
    expect(postedKeys(fetchMock)).toEqual(["key-2"]);
  });

  it("rejects old-account completion rather than overwriting the new account cart", async () => {
    authState.session = session("user-a", "session-a");
    let finishFirst!: (response: Response) => void;
    let posts = 0;
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url.endsWith("/cart/items") && ++posts === 1) {
        return new Promise<Response>((resolve) => {
          finishFirst = resolve;
        });
      }
      return Response.json({ ...cart, cart_id: "cart-b" });
    });
    vi.stubGlobal("fetch", fetchMock);
    const state = renderHook(() => useCartStore());
    const first = addCartItem("listing-1", 2);
    const outcome = first.catch((error: unknown) => error);
    await vi.waitFor(() => expect(posts).toBe(1));
    authState.session = session("user-b", "session-b");
    await act(async () => {
      await addCartItem("listing-1", 2);
    });
    await act(async () => {
      finishFirst(Response.json({ ...cart, cart_id: "cart-a" }));
      await outcome;
    });
    expect(await outcome).toMatchObject({ code: "cart.session_changed" });
    expect(state.result.current.cart?.cart_id).toBe("cart-b");
  });

  it("rotates guest scope after an observed sign-in and sign-out", async () => {
    let posts = 0;
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url.endsWith("/cart/items") && ++posts === 1) throw new Error("lost guest response");
      return Response.json(cart);
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(addCartItem("listing-1", 2)).rejects.toThrow();
    authState.session = session("user-a", "session-a");
    await addCartItem("listing-1", 2);
    authState.session = null;
    await addCartItem("listing-1", 2);
    expect(postedKeys(fetchMock)).toEqual(["key-1", "key-2", "key-3"]);
    const final = [...fetchMock.mock.calls]
      .reverse()
      .find(([url]) => String(url).endsWith("/cart/items"));
    expect(new Headers(final?.[1]?.headers).get("Authorization")).toBeNull();
    expect(final?.[1]?.credentials).toBe("include");
  });

  it("does not reinterpret an auth lookup failure as a guest request", async () => {
    authState.error = { message: "synthetic session storage error" };
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(addCartItem("listing-1", 2)).rejects.toThrow("Cart session unavailable");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("models server replay before changed price/stock validation and emits only on apply", async () => {
    // Offline protocol model only; native/API authority is separately proven by R9.
    const claims = new Set<string>();
    let stock = 4;
    let price = 1000;
    let appliedEvents = 0;
    let interrupted = false;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/cart/items")) {
        const key = new Headers(init?.headers).get("Idempotency-Key")!;
        if (!claims.has(key)) {
          if (stock === 0)
            return Response.json(
              {
                error: {
                  code: "cart.out_of_stock",
                  message: "Synthetic stock cap",
                },
              },
              { status: 409 },
            );
          claims.add(key);
          ++appliedEvents;
          if (!interrupted) {
            interrupted = true;
            throw new Error("response lost after model commit");
          }
        }
      }
      return Response.json({
        ...cart,
        notices: [
          {
            listing_id: "listing-1",
            kind: "price_changed",
            requested_qty: 2,
            available_qty: stock,
            snapshot_price_ngwee: 1000,
            current_price_ngwee: price,
          },
        ],
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(addCartItem("listing-1", 2)).rejects.toThrow();
    stock = 0;
    price = 900;
    const replay = await addCartItem("listing-1", 2);
    expect(replay.notices?.[0]?.current_price_ngwee).toBe(900);
    await expect(addCartItem("listing-1", 2)).rejects.toMatchObject({
      code: "cart.out_of_stock",
    });
    expect(postedKeys(fetchMock)).toEqual(["key-1", "key-1", "key-2"]);
    expect(appliedEvents).toBe(1);
  });

  it("does not claim deduplication after an unobserved HTTP-only guest cookie changes carts", async () => {
    // A fetch stub cannot observe or implement a real browser HTTP-only cookie jar.
    const claims = new Set<string>();
    const appliedCarts: string[] = [];
    let serverCart = "cart-a";
    let lost = false;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/cart/items")) {
        const key = new Headers(init?.headers).get("Idempotency-Key")!;
        const claim = `${serverCart}:${key}`;
        if (!claims.has(claim)) {
          claims.add(claim);
          appliedCarts.push(serverCart);
        }
        if (!lost) {
          lost = true;
          throw new Error("guest response and cookie unobserved");
        }
      }
      return Response.json({ ...cart, cart_id: serverCart });
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(addCartItem("listing-1", 2)).rejects.toThrow();
    serverCart = "cart-b";
    await addCartItem("listing-1", 2);
    expect(postedKeys(fetchMock)).toEqual(["key-1", "key-1"]);
    expect(appliedCarts).toEqual(["cart-a", "cart-b"]);
  });
});

describe("ordered auth observations", () => {
  it("rejects a delayed opaque-token fingerprint without retiring a newer account", async () => {
    let finishDigest!: (value: ArrayBuffer) => void;
    const digest = vi.fn(
      () =>
        new Promise<ArrayBuffer>((resolve) => {
          finishDigest = resolve;
        }),
    );
    vi.stubGlobal("crypto", {
      randomUUID: vi.fn(() => "key-b"),
      subtle: { digest },
    });
    authState.session = { access_token: "opaque-a", user: { id: "user-a" } };
    const fetchMock = vi.fn(async () => Response.json({ ...cart, cart_id: "cart-b" }));
    vi.stubGlobal("fetch", fetchMock);
    const older = addCartItem("listing-1", 1).catch((error: unknown) => error);
    await vi.waitFor(() => expect(digest).toHaveBeenCalledOnce());
    authState.session = session("user-b", "session-b");
    await addCartItem("listing-1", 1);
    finishDigest(new Uint8Array(32).buffer);
    expect(await older).toMatchObject({ code: "cart.session_changed" });
    const { result } = renderHook(() => useCartStore());
    expect(result.current.cart?.cart_id).toBe("cart-b");
    expect(result.current.loading).toBe(false);
    expect(postedKeys(fetchMock)).toEqual(["key-b"]);
  });

  it("normalizes concurrent guest snapshots to the observed logout generation", async () => {
    authState.session = session("user-a", "session-a");
    const fetchMock = vi.fn(async () => Response.json(cart));
    vi.stubGlobal("fetch", fetchMock);
    await addCartItem("listing-1", 1);
    const releases: Array<() => void> = [];
    authState.snapshotRead = () =>
      new Promise((resolve) =>
        releases.push(() => resolve({ data: { session: null }, error: null })),
      );
    const first = addCartItem("listing-1", 1);
    const second = addCartItem("listing-1", 1);
    await vi.waitFor(() => expect(releases).toHaveLength(2));
    authState.snapshotRead = null;
    authState.session = null;
    releases[0]!();
    releases[1]!();
    await Promise.all([first, second]);
    expect(sessionStorage.getItem("vergeo-cart-guest-generation:v2")).toBe("1");
    expect(postedKeys(fetchMock)).toEqual(["key-1", "key-2", "key-3"]);
  });

  it("keeps in-memory retry isolation when session storage is unavailable", async () => {
    const get = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const remove = vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    let attempts = 0;
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/cart/items") && ++attempts === 1) throw new Error("lost");
      return Response.json(cart);
    });
    vi.stubGlobal("fetch", fetchMock);
    try {
      await expect(addCartItem("listing-1", 1)).rejects.toThrow();
      await addCartItem("listing-1", 1);
      authState.session = session("user-a", "session-a");
      await addCartItem("listing-1", 1);
      authState.session = null;
      await addCartItem("listing-1", 1);
      expect(postedKeys(fetchMock)).toEqual(["key-1", "key-1", "key-2", "key-3"]);
    } finally {
      get.mockRestore();
      set.mockRestore();
      remove.mockRestore();
    }
  });
});

it("refuses an older-account read after the new-account cart is loaded", async () => {
  let completeOld!: (response: Response) => void;
  let gets = 0;
  authState.session = session("user-a", "session-a");
  const fetchMock = vi.fn(async (url: string) => {
    if (url.endsWith("/cart") && ++gets === 1)
      return new Promise<Response>((resolve) => {
        completeOld = resolve;
      });
    return Response.json({
      ...cart,
      cart_id: "cart-b",
      notices: [
        {
          listing_id: "listing-b",
          kind: "out_of_stock",
          requested_qty: 1,
          available_qty: 0,
          snapshot_price_ngwee: 100,
          current_price_ngwee: 100,
        },
      ],
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  const older = refreshCart();
  await vi.waitFor(() => expect(gets).toBe(1));
  authState.session = session("user-b", "session-b");
  await refreshCart();
  completeOld(Response.json({ ...cart, cart_id: "cart-a" }));
  await older;
  const { result } = renderHook(() => useCartStore());
  expect(result.current.cart?.cart_id).toBe("cart-b");
  expect(result.current.notices[0]?.listing_id).toBe("listing-b");
});

it.each(["product_id", "product_slug"])(
  "rejects malformed save-for-later %s before wishlist side effects",
  async (field) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({
          cart,
          product_id: null,
          product_slug: null,
          [field]: {},
        }),
      ),
    );
    await expect(saveCartItemForLater("listing-1")).rejects.toMatchObject({
      code: "invalid_response",
    });
  },
);

it("stops old-account wishlist side effects when notice revalidation observes a switch", async () => {
  authState.session = session("user-a", "session-a");
  const withoutNotices = { ...cart, notices: undefined };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/save-for-later"))
        return Response.json({
          cart: withoutNotices,
          product_id: "product-a",
          product_slug: "product-a",
        });
      if (url.endsWith("/revalidate")) {
        authState.session = session("user-b", "session-b");
        return Response.json({ notices: [] });
      }
      return Response.json(cart);
    }),
  );
  await expect(saveCartItemForLater("listing-1")).rejects.toMatchObject({
    code: "cart.session_changed",
  });
  expect(upsertWishlistLocal).not.toHaveBeenCalled();
  expect(syncWishlistWithServer).not.toHaveBeenCalled();
});
