// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen } from "@testing-library/react";
import { ApiError } from "@vergeo/config";
import { renderToString } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({
  session: { user: { id: "A" }, access_token: "token-A" } as {
    user: { id: string };
    access_token: string;
  } | null,
  generation: 1,
  loading: false,
  serverAccount: "A",
  denyB: false,
  listeners: new Set<() => void>(),
  snapshot: null as null | {
    session: { user: { id: string }; access_token: string } | null;
    generation: number;
    loading: boolean;
  },
}));
const mocks = vi.hoisted(() => ({ refresh: vi.fn() }));

vi.mock("../../../../lib/customer-session", async () => {
  const { useSyncExternalStore } = await import("react");
  return {
    useSession: () =>
      useSyncExternalStore(
        (listener) => {
          auth.listeners.add(listener);
          return () => auth.listeners.delete(listener);
        },
        () => auth.snapshot,
        () => auth.snapshot,
      ),
  };
});
vi.mock("@vergeo/auth/server-client", () => ({
  createServerClient: () => ({
    auth: {
      getUser: async () => ({ data: { user: { id: auth.serverAccount } } }),
      getSession: async () => ({
        data: {
          session: {
            user: { id: auth.serverAccount },
            access_token: `token-${auth.serverAccount}`,
          },
        },
      }),
    },
  }),
}));
vi.mock("next/headers", () => ({ cookies: async () => ({}) }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: mocks.refresh }),
  notFound: () => {
    throw new Error("notFound");
  },
  redirect: (url: string) => {
    throw new Error(`redirect ${url}`);
  },
}));
vi.mock("next-intl/server", () => ({
  getMessages: async () => ({}),
  setRequestLocale: () => undefined,
}));
vi.mock("next-intl", () => ({
  createTranslator: () => (key: string, values?: Record<string, string | number>) =>
    `${key}${values ? ` ${Object.values(values).join(" ")}` : ""}`,
}));
vi.mock("./_components/orders-api", () => ({
  createOrdersApiClient: (getToken: () => string) => ({
    listOrders: async () => {
      const account = (await getToken()).endsWith("B") ? "B" : "A";
      if (account === "B" && auth.denyB) {
        throw new ApiError("forbidden", "Forbidden", { status: 403 });
      }
      return {
        groups: [
          {
            checkout_group_id: `group-${account}`,
            created_at: "2026-10-01T00:00:00Z",
            total_ngwee: 1000,
            orders: [
              {
                id: `order-${account}`,
                vendor_id: `vendor-${account}`,
                vendor_name: `Private vendor ${account}`,
                status: "delivered",
                fulfilment: "pickup",
                cod: true,
                paid: false,
                payment_mode: "cod",
                total_ngwee: 1000,
                item_count: 1,
                created_at: "2026-10-01T00:00:00Z",
              },
            ],
          },
        ],
      };
    },
    getOrder: async (id: string) => {
      const account = (await getToken()).endsWith("B") ? "B" : "A";
      if (id !== `order-${account}` || (account === "B" && auth.denyB)) {
        throw new ApiError("forbidden", "Forbidden", { status: 403 });
      }
      return {
        id,
        checkout_group_id: `group-${account}`,
        vendor_id: `vendor-${account}`,
        vendor_name: `Private vendor ${account}`,
        status: "delivered",
        fulfilment: "pickup",
        cod: true,
        paid: false,
        payment_mode: "cod",
        delivery_fee_ngwee: 0,
        subtotal_ngwee: 1000,
        total_ngwee: 1000,
        created_at: "2026-10-01T00:00:00Z",
        items: [
          {
            id: `item-${account}`,
            title: `Private item ${account}`,
            qty: 1,
            unit_price_ngwee: 1000,
          },
        ],
        timeline: [],
        pickup: { qr_token: `Private pickup QR ${account}`, pin: null, stub: false },
        invoice: null,
        related_orders: [],
      };
    },
  }),
}));
vi.mock("./[id]/_components/dispatch-timeline", () => ({
  buildDispatchStatusUpdates: () => [],
  extractDispatchFromEvents: () => ({}),
  DispatchTimeline: () => null,
}));
vi.mock("./[id]/_components/confirm-received", () => ({
  ConfirmReceivedBlock: ({ orderId }: { orderId: string }) => (
    <button data-order-action={orderId}>Confirm</button>
  ),
}));
vi.mock("./[id]/_components/review-prompt", () => ({ ReviewPromptBlock: () => null }));
vi.mock("./[id]/_components/report-problem", () => ({ ReportProblemBlock: () => null }));
vi.mock("./[id]/_components/order-post-delivery-actions", () => ({
  OrderPostDeliveryActions: () => null,
}));
vi.mock("./_components/invoice-link", () => ({ InvoiceLinkBlock: () => null }));
vi.mock("./_components/order-timeline", () => ({ OrderTimeline: () => null }));

import OrderDetailPage from "./[id]/page";
import OrdersPage from "./page";

const listParams = Promise.resolve({ locale: "en" });
const detailParams = (id: string) => Promise.resolve({ locale: "en", id });

function publish() {
  act(() => {
    auth.snapshot = { session: auth.session, loading: auth.loading, generation: auth.generation };
    auth.listeners.forEach((listener) => listener());
  });
}

afterEach(() => {
  cleanup();
  auth.session = { user: { id: "A" }, access_token: "token-A" };
  auth.generation = 1;
  auth.loading = false;
  auth.serverAccount = "A";
  auth.denyB = false;
  auth.snapshot = null;
  auth.listeners.clear();
  mocks.refresh.mockReset();
});

it("orders list hides A vendor and order link on B transition; fresh B renders", async () => {
  publish();
  const staleA = await OrdersPage({ params: listParams });
  const view = render(staleA);
  expect(screen.getByText(/Private vendor A/)).toBeInTheDocument();
  expect(view.container.querySelector('a[href$="order-A"]')).not.toBeNull();

  auth.session = null;
  auth.loading = true;
  auth.generation = 2;
  publish();
  expect(screen.queryAllByText(/Private vendor A/)).toHaveLength(0);
  auth.session = { user: { id: "B" }, access_token: "token-B" };
  auth.loading = false;
  auth.serverAccount = "B";
  publish();
  expect(view.container.querySelector('a[href$="order-A"]')).toBeNull();
  expect(mocks.refresh).toHaveBeenCalled();
  view.rerender(await OrdersPage({ params: listParams }));
  expect(screen.getByText(/Private vendor B/)).toBeInTheDocument();
  view.rerender(staleA);
  expect(screen.queryAllByText(/Private vendor A/)).toHaveLength(0);
});

it("order detail hides A pickup QR, item, and action on B transition; fresh B renders", async () => {
  publish();
  const staleA = await OrderDetailPage({ params: detailParams("order-A") });
  const view = render(staleA);
  expect(screen.getByText("Private pickup QR A")).toBeInTheDocument();
  expect(view.container.querySelector('[data-order-action="order-A"]')).not.toBeNull();

  auth.session = { user: { id: "B" }, access_token: "token-B" };
  auth.generation = 2;
  auth.serverAccount = "B";
  publish();
  expect(screen.queryByText("Private pickup QR A")).not.toBeInTheDocument();
  expect(screen.queryByText(/Private item A/)).not.toBeInTheDocument();
  expect(view.container.querySelector('[data-order-action="order-A"]')).toBeNull();
  view.rerender(await OrderDetailPage({ params: detailParams("order-B") }));
  expect(screen.getByText("Private pickup QR B")).toBeInTheDocument();
  view.rerender(staleA);
  expect(screen.queryByText("Private pickup QR A")).not.toBeInTheDocument();
});

it("orders list and detail hide A on signout and after denied B refresh", async () => {
  publish();
  const list = render(await OrdersPage({ params: listParams }));
  const detail = render(await OrderDetailPage({ params: detailParams("order-A") }));
  auth.session = null;
  auth.generation = 2;
  publish();
  expect(screen.queryAllByText(/Private vendor A/)).toHaveLength(0);
  expect(screen.queryByText("Private pickup QR A")).not.toBeInTheDocument();
  expect(list.container.querySelector('a[href$="order-A"]')).toBeNull();
  expect(detail.container.querySelector('[data-order-action="order-A"]')).toBeNull();

  auth.session = { user: { id: "B" }, access_token: "token-B" };
  auth.generation = 3;
  auth.serverAccount = "B";
  auth.denyB = true;
  publish();
  await expect(OrdersPage({ params: listParams })).rejects.toMatchObject({ status: 403 });
  await expect(OrderDetailPage({ params: detailParams("order-A") })).rejects.toMatchObject({
    status: 403,
  });
  expect(screen.queryByText("Private pickup QR A")).not.toBeInTheDocument();
});

it("same-account token refresh keeps both order pages visible without router refresh", async () => {
  publish();
  render(await OrdersPage({ params: listParams }));
  render(await OrderDetailPage({ params: detailParams("order-A") }));
  auth.session = { user: { id: "A" }, access_token: "token-A-new" };
  publish();
  expect(screen.getAllByText(/Private vendor A/).length).toBeGreaterThan(0);
  expect(screen.getByText("Private pickup QR A")).toBeInTheDocument();
  expect(mocks.refresh).not.toHaveBeenCalled();
});

it("SSR includes authenticated order content and a late A mount under B stays hidden", async () => {
  publish();
  const listA = await OrdersPage({ params: listParams });
  const detailA = await OrderDetailPage({ params: detailParams("order-A") });
  expect(renderToString(listA)).toContain("Private vendor A");
  expect(renderToString(detailA)).toContain("Private pickup QR A");

  auth.session = { user: { id: "B" }, access_token: "token-B" };
  auth.generation = 2;
  publish();
  const list = render(listA);
  const detail = render(detailA);
  expect(list.container.querySelector('a[href$="order-A"]')).toBeNull();
  expect(detail.container.querySelector('[data-order-action="order-A"]')).toBeNull();
  expect(screen.queryByText("Private pickup QR A")).not.toBeInTheDocument();
});
