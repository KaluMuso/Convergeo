// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TodayBoard } from "./TodayBoard";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const api = vi.hoisted(() => ({ request: vi.fn(), products: vi.fn() }));

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
vi.mock("next/link", () => ({
  default: ({ children, href, ...rest }: React.ComponentProps<"a">) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock("./api", () => ({ dashboardApi: { request: api.request } }));
vi.mock("../moderation/products/_components/api", () => ({
  listPendingCanonicalProducts: api.products,
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

let root: Root | undefined;
let container: HTMLDivElement;

beforeEach(() => {
  api.request.mockReset();
  api.products.mockReset();
  container = document.createElement("div");
  document.body.append(container);
});

afterEach(async () => {
  await act(async () => root?.unmount());
  container.remove();
  root = undefined;
});

async function mount() {
  root = createRoot(container);
  await act(async () => {
    root?.render(<TodayBoard locale="en" placedCount={3} placedLoading={false} />);
  });
}

const card = (id: string) => container.querySelector(`[data-testid="${id}"]`)!;

describe("TodayBoard streaming", () => {
  it("paints each card as its own request settles, without waiting for the slowest", async () => {
    const slowDisputes = deferred<unknown[]>();
    api.request.mockImplementation((path: string) => {
      if (path.startsWith("/admin/vendors")) return Promise.resolve([{}, {}]);
      if (path === "/admin/disputes") return slowDisputes.promise;
      return Promise.resolve({ flag_enabled: true, ready_orders: [{}] });
    });
    api.products.mockResolvedValue([{}, {}, {}, {}]);
    await mount();

    expect(card("today-kyc").textContent).toContain("2");
    expect(card("today-products").textContent).toContain("4");
    expect(card("today-dispatch").textContent).toContain("1");
    // The slow request is still pending: only its card shows the loading state.
    expect(card("today-disputes").querySelector('[role="status"]')).not.toBeNull();
    expect(card("today-kyc").querySelector('[role="status"]')).toBeNull();

    await act(async () => slowDisputes.resolve([{}]));
    expect(card("today-disputes").querySelector('[role="status"]')).toBeNull();
    expect(card("today-disputes").textContent).toContain("1");
  });

  it("ignores a superseded load when Refresh is pressed while one is in flight", async () => {
    const first = deferred<unknown[]>();
    let kycCalls = 0;
    api.request.mockImplementation((path: string) => {
      if (path.startsWith("/admin/vendors")) {
        kycCalls += 1;
        return kycCalls === 1 ? first.promise : Promise.resolve([{}, {}, {}]);
      }
      if (path === "/admin/disputes") return Promise.resolve([]);
      return Promise.resolve({ flag_enabled: true, ready_orders: [] });
    });
    api.products.mockResolvedValue([]);
    await mount();
    await act(async () => {
      container.querySelector<HTMLButtonElement>("header button")!.click();
    });
    expect(card("today-kyc").textContent).toContain("3");
    await act(async () => first.resolve([{}]));
    expect(card("today-kyc").textContent).toContain("3");
  });
});
