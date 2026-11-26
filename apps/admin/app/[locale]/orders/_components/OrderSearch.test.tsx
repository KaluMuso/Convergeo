// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ORDERS_PAGE_SIZE, OrderSearch, orderSearchParams, shortOrderRef } from "./OrderSearch";

const mocks = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("next-intl", () => ({ useTranslations: (ns: string) => (key: string) => `${ns}.${key}` }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, ordersApi: { request: mocks.request } };
});
vi.mock("@vergeo/auth", () => ({ getBrowserAccessToken: async () => "t" }));
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let root: ReturnType<typeof createRoot>;
let host: HTMLDivElement;

function setInputValue(el: HTMLInputElement, value: string) {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

function order(index: number) {
  const suffix = String(index).padStart(12, "0");
  return {
    id: `abcdef${String(index).padStart(2, "0")}-0000-4000-8000-${suffix}`,
    status: "placed",
    fulfilment: "delivery",
    vendor_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    vendor_display_name: "Lusaka Electronics",
    vendor_slug: "lusaka-electronics",
    customer_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    customer_phone: "+260971234567",
    customer_display_name: "Jane Customer",
    total_ngwee: 123456,
    created_at: new Date(Date.UTC(2026, 10, 25, 10, 0, 0) - index * 60_000).toISOString(),
  };
}

beforeEach(() => {
  mocks.request.mockReset();
  window.history.replaceState({}, "", "/en/orders");
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  document.body.innerHTML = "";
});

describe("OrderSearch", () => {
  it("shows empty state when search returns no orders", async () => {
    mocks.request.mockResolvedValue([]);
    await act(async () => root.render(<OrderSearch locale="en" />));
    await act(async () => {
      setInputValue(host.querySelectorAll("input")[1]!, "+260970000000");
      (host.querySelector("form") as HTMLFormElement).requestSubmit();
    });
    await vi.waitFor(() =>
      expect(host.querySelector('[data-testid="orders-search-empty"]')).toBeTruthy(),
    );
    expect(host.textContent).toContain("admin.boards.states.orders.emptyTitle");
  });

  it("opens on the newest orders with name, short ref, total and date, never the raw id", async () => {
    mocks.request.mockResolvedValue([order(1)]);
    await act(async () => root.render(<OrderSearch locale="en" />));
    await vi.waitFor(() =>
      expect(host.querySelector('[data-testid="orders-results-table"]')).toBeTruthy(),
    );
    expect(mocks.request).toHaveBeenCalledWith("/admin/orders/search");
    const table = host.querySelector('[data-testid="orders-results-table"]')!;
    expect(table.textContent).toContain("Jane Customer");
    expect(table.textContent).toContain(shortOrderRef(order(1).id));
    expect(table.textContent).toContain("K1,234.56");
    expect(table.textContent).not.toContain(order(1).id);
    expect(host.textContent).toContain("admin.orders.search.recentHeading");
    expect(host.querySelector('[data-testid="orders-load-more"]')).toBeNull();
  });

  it("loads the next page of recent orders from the last created_at", async () => {
    const firstPage = Array.from({ length: ORDERS_PAGE_SIZE }, (_, index) => order(index));
    mocks.request.mockResolvedValueOnce(firstPage).mockResolvedValueOnce([order(99)]);
    await act(async () => root.render(<OrderSearch locale="en" />));
    const more = await vi.waitFor(() => {
      const node = host.querySelector<HTMLButtonElement>('[data-testid="orders-load-more"]');
      expect(node).toBeTruthy();
      return node!;
    });
    await act(async () => more.click());
    const last = firstPage[firstPage.length - 1]!;
    expect(mocks.request).toHaveBeenLastCalledWith(
      `/admin/orders/search?${new URLSearchParams({
        before: last.created_at,
        before_id: last.id,
      }).toString()}`,
    );
    await vi.waitFor(() =>
      expect(host.querySelectorAll('[data-testid="orders-results-table"] tbody tr')).toHaveLength(
        ORDERS_PAGE_SIZE + 1,
      ),
    );
  });

  it("builds query params from filters and the cursor", () => {
    expect(
      orderSearchParams(
        { orderId: "", phone: " 0971 ", vendor: "", status: "placed" },
        null,
      ).toString(),
    ).toBe("phone=0971&status=placed");
    expect(
      orderSearchParams({ orderId: "", phone: "", vendor: "", status: "" }, null).toString(),
    ).toBe("");
  });
});
