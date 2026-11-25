// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OrderSearch } from "./OrderSearch";

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
});
