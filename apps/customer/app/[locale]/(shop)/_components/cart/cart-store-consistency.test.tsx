// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import {
  act,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: { getSession: async () => ({ data: { session: null } }) },
  }),
}));
vi.mock("../../../../../lib/api-base-url", () => ({
  getApiBaseUrl: () => "https://api.example.test",
}));

import {
  refreshCart,
  setStoreStateForTests,
  updateCartItemQty,
  useCartStore,
  type CartResponse,
} from "./mini-cart-drawer";
import { QtyStepper } from "./qty-stepper";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function cart(qty: number): CartResponse {
  const line = {
    id: "line-1",
    listing_id: "listing-1",
    vendor_id: "vendor-1",
    qty,
    unit_price_ngwee: 50_000,
    line_total_ngwee: qty * 50_000,
    wholesale: false,
    title_override: "Phone",
  };
  return {
    cart_id: "cart-1",
    items: [line],
    vendor_groups: [
      {
        vendor_id: "vendor-1",
        items: [line],
        subtotal_ngwee: line.line_total_ngwee,
        delivery_eligible: false,
      },
    ],
    subtotal_ngwee: line.line_total_ngwee,
    conflicts: [],
    notices: [],
  };
}

function json(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  setStoreStateForTests({
    cart: null,
    notices: [],
    loading: false,
    loadError: false,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("cart response ordering", () => {
  it("keeps a quantity update and its price after an older refresh completes", async () => {
    const oldGet = deferred<Response>();
    const requests: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = new URL(String(input)).pathname;
        requests.push(`${init?.method ?? "GET"} ${path}`);
        if (path === "/cart" && !init?.method) return oldGet.promise;
        if (path === "/cart/items/listing-1")
          return Promise.resolve(json(cart(3)));
        if (path === "/cart/revalidate")
          return Promise.resolve(json({ notices: [] }));
        throw new Error(`Unexpected request ${path}`);
      }),
    );

    const state = renderHook(() => useCartStore());
    let pendingRefresh!: Promise<CartResponse | null>;
    await act(async () => {
      pendingRefresh = refreshCart();
    });
    await act(async () => {
      await updateCartItemQty("listing-1", 3);
    });
    expect(state.result.current.cart?.items[0]?.qty).toBe(3);
    expect(state.result.current.cart?.subtotal_ngwee).toBe(150_000);

    await act(async () => {
      oldGet.resolve(json(cart(2)));
      await pendingRefresh;
    });

    expect(state.result.current.cart?.items[0]?.qty).toBe(3);
    expect(state.result.current.cart?.subtotal_ngwee).toBe(150_000);
    expect(state.result.current.loading).toBe(false);
    expect(requests).toContain("PATCH /cart/items/listing-1");
  });

  it("ignores an old refresh started while a quantity update is pending", async () => {
    const pendingPatch = deferred<Response>();
    const oldGet = deferred<Response>();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = new URL(String(input)).pathname;
        if (path === "/cart/items/listing-1" && init?.method === "PATCH")
          return pendingPatch.promise;
        if (path === "/cart" && !init?.method) return oldGet.promise;
        if (path === "/cart/revalidate")
          return Promise.resolve(json({ notices: [] }));
        throw new Error(`Unexpected request ${path}`);
      }),
    );

    const state = renderHook(() => useCartStore());
    let pendingUpdate!: Promise<CartResponse>;
    let pendingRefresh!: Promise<CartResponse | null>;
    await act(async () => {
      pendingUpdate = updateCartItemQty("listing-1", 3);
      pendingRefresh = refreshCart();
    });
    await act(async () => {
      pendingPatch.resolve(json(cart(3)));
      await pendingUpdate;
    });
    expect(state.result.current.cart?.subtotal_ngwee).toBe(150_000);

    await act(async () => {
      oldGet.resolve(json(cart(2)));
      await pendingRefresh;
    });
    expect(state.result.current.cart?.items[0]?.qty).toBe(3);
    expect(state.result.current.cart?.subtotal_ngwee).toBe(150_000);
  });

  it("reconciles server truth when overlapping updates finish out of order", async () => {
    const firstPatch = deferred<Response>();
    const secondPatch = deferred<Response>();
    let patchCount = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname;
      if (path === "/cart/items/listing-1" && init?.method === "PATCH") {
        patchCount += 1;
        return patchCount === 1 ? firstPatch.promise : secondPatch.promise;
      }
      if (path === "/cart") return Promise.resolve(json(cart(3)));
      if (path === "/cart/revalidate")
        return Promise.resolve(json({ notices: [] }));
      throw new Error(`Unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const state = renderHook(() => useCartStore());
    let first!: Promise<CartResponse>;
    let second!: Promise<CartResponse>;
    await act(async () => {
      first = updateCartItemQty("listing-1", 3);
      second = updateCartItemQty("listing-1", 4);
    });
    await act(async () => {
      secondPatch.resolve(json(cart(4)));
      await second;
    });
    expect(state.result.current.cart?.items[0]?.qty).toBe(4);

    await act(async () => {
      firstPatch.resolve(json(cart(3)));
      await first;
    });
    await waitFor(() =>
      expect(state.result.current.cart?.items[0]?.qty).toBe(3),
    );
    expect(state.result.current.cart?.subtotal_ngwee).toBe(150_000);
    expect(
      fetchMock.mock.calls.some(
        ([input]) => new URL(String(input)).pathname === "/cart",
      ),
    ).toBe(true);
  });

  it("keeps the later reconciliation when an earlier read finishes last", async () => {
    const firstPatch = deferred<Response>();
    const secondPatch = deferred<Response>();
    const oldRead = deferred<Response>();
    const finalRead = deferred<Response>();
    let patchCount = 0;
    let readCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = new URL(String(input)).pathname;
        if (path === "/cart/items/listing-1" && init?.method === "PATCH") {
          patchCount += 1;
          return patchCount === 1 ? firstPatch.promise : secondPatch.promise;
        }
        if (path === "/cart") {
          readCount += 1;
          return readCount === 1 ? oldRead.promise : finalRead.promise;
        }
        if (path === "/cart/revalidate")
          return Promise.resolve(json({ notices: [] }));
        throw new Error(`Unexpected request ${path}`);
      }),
    );
    const state = renderHook(() => useCartStore());
    let first!: Promise<CartResponse>;
    let second!: Promise<CartResponse>;
    await act(async () => {
      first = updateCartItemQty("listing-1", 3);
      second = updateCartItemQty("listing-1", 4);
    });
    await act(async () => {
      secondPatch.resolve(json(cart(4)));
      await second;
    });
    let pendingOldRead!: Promise<CartResponse | null>;
    await act(async () => {
      pendingOldRead = refreshCart();
    });

    await act(async () => {
      firstPatch.resolve(json(cart(3)));
      await first;
    });
    expect(readCount).toBe(2);
    await act(async () => {
      finalRead.resolve(json(cart(3)));
    });
    await waitFor(() =>
      expect(state.result.current.cart?.items[0]?.qty).toBe(3),
    );
    await act(async () => {
      oldRead.resolve(json(cart(4)));
      await pendingOldRead;
    });
    expect(state.result.current.cart?.items[0]?.qty).toBe(3);
    expect(state.result.current.cart?.subtotal_ngwee).toBe(150_000);
  });

  it("re-reads the server cart when a quantity response is interrupted", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname;
      if (path === "/cart/items/listing-1" && init?.method === "PATCH") {
        return Promise.reject(new TypeError("connection lost"));
      }
      if (path === "/cart") return Promise.resolve(json(cart(3)));
      if (path === "/cart/revalidate")
        return Promise.resolve(json({ notices: [] }));
      throw new Error(`Unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const state = renderHook(() => useCartStore());

    await act(async () => {
      await expect(updateCartItemQty("listing-1", 3)).rejects.toThrow();
    });
    await waitFor(() =>
      expect(state.result.current.cart?.items[0]?.qty).toBe(3),
    );
    expect(state.result.current.cart?.subtotal_ngwee).toBe(150_000);
    expect(state.result.current.loading).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});

describe("cart quantity submission", () => {
  it("holds a second click while the first quantity update is pending", async () => {
    const pending = deferred<void>();
    const onChange = vi.fn(() => pending.promise);
    const user = userEvent.setup();
    render(
      <QtyStepper
        value={2}
        min={1}
        max={5}
        labels={{
          decrease: "Decrease",
          increase: "Increase",
          value: "Quantity {count}",
          updating: "Updating",
          decreaseSymbol: "−",
          increaseSymbol: "+",
        }}
        onChange={onChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Increase" }));
    expect(screen.getByRole("button", { name: "Increase" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Increase" }));
    expect(onChange).toHaveBeenCalledExactlyOnceWith(3);

    await act(async () => {
      pending.resolve();
      await pending.promise;
    });
  });
});
