// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
  merge: vi.fn(),
  fetch: vi.fn(),
}));

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: { getSession: mocks.getSession, onAuthStateChange: mocks.onAuthStateChange },
  }),
}));
vi.mock("../../../../../lib/cart-merge", () => ({
  mergeGuestCartIntoAccount: mocks.merge,
}));
vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) =>
    <a href={href}>{children}</a>,
}));
vi.mock("@vergeo/ui/src/bottom-sheet", () => ({
  BottomSheet: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div role="dialog">{children}</div> : null,
}));
vi.mock("@vergeo/ui/src/link-button", () => ({
  LinkButton: ({ children, href }: { children: React.ReactNode; href: string }) =>
    <a href={href}>{children}</a>,
}));

const labels = {
  title: "Cart", close: "Close", subtotal: "Subtotal", total: "Total",
  viewCart: "View cart", checkoutCta: "Checkout", emptyTitle: "Empty",
  emptyBody: "No items", emptyTrust: { escrow: "Escrow", delivery: "Delivery", pickup: "Pickup" },
  browseCta: "Browse", openCart: "Open cart", loadErrorTitle: "Unavailable",
  loadErrorBody: "Retry", loadErrorRetry: "Retry", quantityValue: "{count}",
  saleUnits: { each: "each", metre: "metre", kg: "kg", litre: "litre", bag: "bag", sqm: "sqm" },
  madeToOrderLeadTime: "{days}",
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function session(id: string) {
  return { access_token: `token-${id}`, user: { id } };
}

function cart(name: string) {
  return {
    cart_id: `cart-${name}`,
    items: [{
      id: `line-${name}`, listing_id: `listing-${name}`, vendor_id: "vendor",
      qty: 1, unit_price_ngwee: 10000, wholesale: false,
      line_total_ngwee: 10000, title_override: name,
    }],
    vendor_groups: [], subtotal_ngwee: 10000, conflicts: [], notices: [],
  };
}

function response(value: unknown) {
  return { ok: true, headers: new Headers({ "content-type": "application/json" }), json: async () => value };
}

beforeEach(() => {
  vi.resetModules();
  mocks.getSession.mockReset().mockResolvedValue({ data: { session: null }, error: null });
  mocks.onAuthStateChange.mockReset();
  mocks.merge.mockReset();
  mocks.fetch.mockReset().mockImplementation(async (url: string) =>
    response(url.endsWith("/cart/revalidate") ? { notices: [] } : cart("guest")));
  vi.stubGlobal("fetch", mocks.fetch);
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("mounted mini-cart identity barrier", () => {
  it("defers writes through SIGNED_IN, blocks failed reconciliation, then uses the retry identity", async () => {
    let authEvent!: (event: string, value: ReturnType<typeof session> | null) => void;
    mocks.onAuthStateChange.mockImplementation((callback) => {
      authEvent = callback;
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    });
    const pending = deferred<void>();
    mocks.merge.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(undefined);
    const mini = await import("./mini-cart-drawer");
    const customer = await import("../../../../../lib/customer-session");
    render(<mini.CartHost locale="en" labels={labels} />);
    await waitFor(() => expect(mocks.getSession).toHaveBeenCalledOnce());

    authEvent("SIGNED_IN", session("account-a"));
    const add = mini.addCartItem("listing-a", 1);
    await waitFor(() => expect(mocks.merge).toHaveBeenCalledOnce());
    expect(mocks.fetch.mock.calls.filter(([url]) => String(url).endsWith("/cart/items"))).toHaveLength(0);
    pending.reject(new Error("merge failed"));
    await expect(add).rejects.toThrow("merge failed");
    expect(mini.useCartStore).toBeDefined();
    await customer.getReadyCustomerSession(true);
    mocks.fetch.mockResolvedValue(response(cart("account-a")));
    await mini.addCartItem("listing-a", 1);
    const itemCall = mocks.fetch.mock.calls.find(([url]) => String(url).endsWith("/cart/items"));
    expect(new Headers(itemCall?.[1]?.headers).get("Authorization")).toBe("Bearer token-account-a");
    expect(mocks.getSession).toHaveBeenCalledOnce();
  }, 30_000);

  it("drops a late old-account response after logout and account switch", async () => {
    let authEvent!: (event: string, value: ReturnType<typeof session> | null) => void;
    mocks.onAuthStateChange.mockImplementation((callback) => {
      authEvent = callback;
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    });
    mocks.merge.mockResolvedValue(undefined);
    const mini = await import("./mini-cart-drawer");
    const customer = await import("../../../../../lib/customer-session");
    function CartName() {
      const { cart: current } = mini.useCartStore();
      return <span data-testid="cart-name">{current?.items[0]?.title_override ?? "empty"}</span>;
    }
    render(<><mini.CartHost locale="en" labels={labels} /><CartName /></>);
    await waitFor(() => expect(mocks.getSession).toHaveBeenCalledOnce());
    authEvent("SIGNED_IN", session("account-a"));
    await customer.getReadyCustomerSession();
    const late = deferred<ReturnType<typeof response>>();
    mocks.fetch.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).endsWith("/cart/items")) return late.promise;
      const account = new Headers(init?.headers).get("Authorization")?.includes("account-b")
        ? "account-b" : "account-a";
      return Promise.resolve(response(cart(account)));
    });
    const add = mini.addCartItem("listing-a", 1);
    await waitFor(() => expect(mocks.fetch.mock.calls.some(([url]) => String(url).endsWith("/cart/items"))).toBe(true));
    authEvent("SIGNED_OUT", null);
    await waitFor(() => expect(screen.getByTestId("cart-name")).toHaveTextContent("empty"));
    authEvent("SIGNED_IN", session("account-b"));
    await customer.getReadyCustomerSession();
    await waitFor(() => expect(screen.getByTestId("cart-name")).toHaveTextContent("account-b"));
    late.resolve(response(cart("account-a")));
    await expect(add).rejects.toMatchObject({ code: "cart.auth_transition_changed" });
    expect(screen.getByTestId("cart-name")).toHaveTextContent("account-b");
  }, 30_000);
});
