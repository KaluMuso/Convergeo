// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { cloneElement } from "react";
import { afterEach, expect, it, vi } from "vitest";

import accountMessages from "../../../../../../../packages/i18n/messages/en/account.json";

const auth = vi.hoisted(() => ({
  generation: 1,
  session: { access_token: "token-a", user: { id: "account-a" } } as {
    access_token: string;
    user: { id: string };
  } | null,
}));
const mocks = vi.hoisted(() => ({
  serverFetch: vi.fn(),
  apiRequest: vi.fn(),
  refresh: vi.fn(),
  refreshCart: vi.fn(),
}));

vi.mock("../../_components/account-server", () => ({
  getAccountAccessToken: async () => "token-a",
}));
vi.mock("../../../../../lib/api-base-url", () => ({
  getApiBaseUrl: () => "http://api.test",
}));
vi.mock("../../../../../lib/customer-session", () => ({
  useSession: () => ({ ...auth, loading: false, error: null }),
  customerAuth: { snapshot: () => ({ ...auth }) },
  getReadyCustomerSession: async () => auth.session,
}));
vi.mock("../../../(shop)/_components/cart/mini-cart-drawer", () => ({
  refreshCart: mocks.refreshCart,
}));
vi.mock("@vergeo/config", () => {
  class ApiError extends Error {
    code: string;
    status: number;
    constructor(code: string, message: string, options: { status?: number } = {}) {
      super(message);
      this.code = code;
      this.status = options.status ?? 500;
    }
  }
  return {
    ApiError,
    createApiClient: ({ getToken }: { getToken: () => string | null }) => ({
      request: (path: string, options?: unknown) => mocks.apiRequest(getToken(), path, options),
    }),
  };
});
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("not found");
  },
  useRouter: () => ({ refresh: mocks.refresh }),
}));
vi.mock("next-intl/server", () => ({ setRequestLocale: vi.fn() }));

import Page from "./page";

const thread = (name: string, customerId = "account-a", id = `thread-${name}`) => ({
  id,
  customer_id: customerId,
  vendor_id: `vendor-${name}`,
  listing_id: `listing-${name}`,
  service_id: null,
  requested_details: `Private request from ${name}`,
  status: "quoted",
  quote_price_ngwee: 12000,
  quote_valid_until: "2099-01-01T00:00:00Z",
  quoted_at: "2026-10-01T00:00:00Z",
  last_message_at: null,
  created_at: "2026-10-01T00:00:00Z",
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

async function mount(id = "thread-A") {
  mocks.serverFetch.mockResolvedValue({
    ok: true,
    json: async () => thread(id === "thread-A" ? "A" : "B", "account-a", id),
  });
  vi.stubGlobal("fetch", mocks.serverFetch);
  const wrap = (page: Awaited<ReturnType<typeof Page>>) => (
    <NextIntlClientProvider
      locale="en"
      messages={{ account: { listingQuotes: accountMessages.listingQuotes } }}
    >
      {page ? cloneElement(page) : null}
    </NextIntlClientProvider>
  );
  const page = await Page({ params: Promise.resolve({ locale: "en", id }) });
  const view = render(wrap(page));
  return {
    rerender: () => view.rerender(wrap(page)),
    refresh: async () => {
      const refreshedPage = await Page({
        params: Promise.resolve({ locale: "en", id }),
      });
      view.rerender(wrap(refreshedPage));
    },
    navigate: async (nextId: string) => {
      const nextPage = await Page({
        params: Promise.resolve({ locale: "en", id: nextId }),
      });
      view.rerender(wrap(nextPage));
    },
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  auth.generation = 1;
  auth.session = { access_token: "token-a", user: { id: "account-a" } };
});

it("clears A's quote and accept action immediately on B switch and B 403", async () => {
  const { ApiError } = await import("@vergeo/config");
  mocks.apiRequest.mockImplementation((token: string) =>
    token === "token-a"
      ? Promise.resolve(thread("A"))
      : Promise.reject(new ApiError("forbidden", "Forbidden", { status: 403 })),
  );
  const view = await mount();
  expect(await screen.findByText("Private request from A")).toBeInTheDocument();
  expect(screen.getByTestId("listing-quote-accept-cta")).toBeEnabled();
  auth.session = { access_token: "token-b", user: { id: "account-b" } };
  auth.generation++;
  view.rerender();
  expect(screen.queryByText("Private request from A")).not.toBeInTheDocument();
  expect(screen.queryByTestId("listing-quote-accept-cta")).not.toBeInTheDocument();
  expect(await screen.findByText(accountMessages.listingQuotes.status.error)).toBeInTheDocument();
  expect(mocks.apiRequest).toHaveBeenCalledWith("token-b", "/rfq/thread-A", undefined);
});

it("clears the quote and action immediately on signout", async () => {
  mocks.apiRequest.mockResolvedValue(thread("A"));
  const view = await mount();
  expect(await screen.findByText("Private request from A")).toBeInTheDocument();
  auth.session = null;
  auth.generation++;
  view.rerender();
  expect(screen.queryByText("Private request from A")).not.toBeInTheDocument();
  expect(screen.queryByTestId("listing-quote-accept-cta")).not.toBeInTheDocument();
});

it("ignores an old account response after B takes over", async () => {
  const old = deferred<ReturnType<typeof thread>>();
  const { ApiError } = await import("@vergeo/config");
  mocks.apiRequest.mockImplementation((token: string) =>
    token === "token-a"
      ? old.promise
      : Promise.reject(new ApiError("forbidden", "Forbidden", { status: 403 })),
  );
  const view = await mount();
  await waitFor(() =>
    expect(mocks.apiRequest).toHaveBeenCalledWith("token-a", "/rfq/thread-A", undefined),
  );
  auth.session = { access_token: "token-b", user: { id: "account-b" } };
  auth.generation++;
  view.rerender();
  expect(await screen.findByText(accountMessages.listingQuotes.status.error)).toBeInTheDocument();
  await act(async () => old.resolve(thread("A")));
  expect(screen.queryByText("Private request from A")).not.toBeInTheDocument();
  expect(screen.queryByTestId("listing-quote-accept-cta")).not.toBeInTheDocument();
});

it("uses the newest same-account token refresh result", async () => {
  const oldRefresh = deferred<ReturnType<typeof thread>>();
  mocks.apiRequest.mockImplementation((token: string) => {
    if (token === "token-a") return Promise.resolve(thread("A"));
    if (token === "token-refresh-1") return oldRefresh.promise;
    return Promise.resolve(thread("Latest", "account-a", "thread-A"));
  });
  const view = await mount();
  expect(await screen.findByText("Private request from A")).toBeInTheDocument();
  auth.session = { access_token: "token-refresh-1", user: { id: "account-a" } };
  view.rerender();
  await waitFor(() =>
    expect(mocks.apiRequest).toHaveBeenCalledWith("token-refresh-1", "/rfq/thread-A", undefined),
  );
  auth.session = { access_token: "token-refresh-2", user: { id: "account-a" } };
  view.rerender();
  expect(await screen.findByText("Private request from Latest")).toBeInTheDocument();
  await act(async () => oldRefresh.resolve(thread("Stale", "account-a", "thread-A")));
  expect(screen.getByText("Private request from Latest")).toBeInTheDocument();
  expect(screen.queryByText("Private request from Stale")).not.toBeInTheDocument();
});

it("loads the new quote after route navigation", async () => {
  mocks.apiRequest.mockImplementation((_token: string, path: string) =>
    Promise.resolve(path === "/rfq/thread-A" ? thread("A") : thread("B")),
  );
  const view = await mount();
  expect(await screen.findByText("Private request from A")).toBeInTheDocument();
  await view.navigate("thread-B");
  expect(await screen.findByText("Private request from B")).toBeInTheDocument();
  expect(screen.queryByText("Private request from A")).not.toBeInTheDocument();
});

it("reloads a quote after a same-route server refresh", async () => {
  let accepted = false;
  mocks.apiRequest.mockImplementation(() =>
    Promise.resolve({
      ...thread("A"),
      status: accepted ? "accepted" : "quoted",
    }),
  );
  const view = await mount();
  expect(await screen.findByTestId("listing-quote-accept-cta")).toBeEnabled();
  accepted = true;
  mocks.serverFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ ...thread("A"), status: "accepted" }),
  });
  await view.refresh();
  expect(await screen.findByTestId("listing-quote-accepted")).toBeInTheDocument();
  expect(screen.queryByTestId("listing-quote-accept-cta")).not.toBeInTheDocument();
});

it("still accepts a current quote into the cart", async () => {
  mocks.apiRequest.mockImplementation((_token: string, path: string) =>
    Promise.resolve(path === "/rfq/thread-A" ? thread("A") : {}),
  );
  mocks.refreshCart.mockResolvedValue(undefined);
  await mount();
  await userEvent.click(await screen.findByTestId("listing-quote-accept-cta"));
  expect(mocks.apiRequest).toHaveBeenCalledWith("token-a", "/cart/rfq/thread-A/accept", {
    method: "POST",
    body: JSON.stringify({ qty: 1 }),
  });
  expect(await screen.findByTestId("listing-quote-accept-success")).toBeInTheDocument();
  expect(mocks.refresh).toHaveBeenCalled();
});

it("does not finish an in-flight A acceptance after switching to B", async () => {
  const oldAccept = deferred<unknown>();
  mocks.apiRequest.mockImplementation((_token: string, path: string) =>
    path === "/rfq/thread-A" ? Promise.resolve(thread("A")) : oldAccept.promise,
  );
  const view = await mount();
  await userEvent.click(await screen.findByTestId("listing-quote-accept-cta"));
  await waitFor(() =>
    expect(mocks.apiRequest).toHaveBeenCalledWith(
      "token-a",
      "/cart/rfq/thread-A/accept",
      expect.anything(),
    ),
  );

  auth.session = { access_token: "token-b", user: { id: "account-b" } };
  auth.generation++;
  view.rerender();
  expect(screen.queryByText("Private request from A")).not.toBeInTheDocument();
  await act(async () => oldAccept.resolve({}));
  expect(mocks.refreshCart).not.toHaveBeenCalled();
  expect(mocks.refresh).not.toHaveBeenCalled();
  expect(screen.queryByTestId("listing-quote-accept-success")).not.toBeInTheDocument();
});
