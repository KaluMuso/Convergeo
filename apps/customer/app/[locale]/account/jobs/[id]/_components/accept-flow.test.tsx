// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, expect, it, vi } from "vitest";

import servicesMessages from "../../../../../../../../packages/i18n/messages/en/services.json";

import { AcceptFlow } from "./accept-flow";

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  push: vi.fn(),
  getToken: null as null | (() => string | null),
  auth: {
    session: { user: { id: "account-a" }, access_token: "token-a" } as {
      user: { id: string };
      access_token: string;
    } | null,
    generation: 1,
  },
}));

vi.mock("../../../../../../lib/customer-session", () => ({
  useSession: () => mocks.auth,
  customerAuth: { snapshot: () => mocks.auth },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
}));

vi.mock("@vergeo/config", () => {
  class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  }
  return {
    ApiError,
    createApiClient: ({ getToken }: { getToken: () => string | null }) => {
      mocks.getToken = getToken;
      return { request: (...args: unknown[]) => mocks.request(...args) };
    },
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mocks.auth.session = { user: { id: "account-a" }, access_token: "token-a" };
  mocks.auth.generation = 1;
  mocks.getToken = null;
});

const accepted = { checkout_group_id: "checkout-a" };

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function flow(jobId = "job-a", quoteId = "quote-a") {
  return (
    <AcceptFlow
      locale="en"
      jobId={jobId}
      quoteId={quoteId}
      vendorName="Provider A"
      totalNgwee={120_000}
    />
  );
}

function renderFlow(jobId?: string, quoteId?: string) {
  return render(flow(jobId, quoteId), {
    wrapper: ({ children }) => (
      <NextIntlClientProvider
        locale="en"
        messages={{ services: servicesMessages }}
        onError={() => {}}
      >
        {children}
      </NextIntlClientProvider>
    ),
  });
}

async function startPendingAccept() {
  const pending = deferred<typeof accepted>();
  mocks.request.mockReturnValueOnce(pending.promise);
  await userEvent.setup().click(screen.getByRole("button", { name: /pay deposit/i }));
  await waitFor(() => expect(mocks.request).toHaveBeenCalledTimes(1));
  return pending;
}

it("does not navigate when acceptance completes after unmount", async () => {
  const view = renderFlow();
  const pending = await startPendingAccept();
  view.unmount();
  await act(async () => pending.resolve(accepted));
  expect(mocks.push).not.toHaveBeenCalled();
  expect(mocks.request).toHaveBeenCalledTimes(1);
});

it("does not navigate or show A's accept error after switching accounts", async () => {
  const view = renderFlow();
  const pending = await startPendingAccept();
  mocks.auth.session = { user: { id: "account-b" }, access_token: "token-b" };
  mocks.auth.generation = 2;
  view.rerender(flow());
  await act(async () => pending.reject(new Error("A failed")));
  expect(mocks.push).not.toHaveBeenCalled();
  expect(screen.queryByText(/could not start the deposit/i)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /pay deposit/i })).toBeEnabled();
});

it("does not send A's completed checkout to B after switching accounts", async () => {
  const view = renderFlow();
  const pending = await startPendingAccept();
  mocks.auth.session = { user: { id: "account-b" }, access_token: "token-b" };
  mocks.auth.generation = 2;
  view.rerender(flow());
  await act(async () => pending.resolve(accepted));
  expect(mocks.push).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: /pay deposit/i })).toBeEnabled();
});

it("does not navigate when auth publishes B before React rerenders", async () => {
  const view = renderFlow();
  const pending = await startPendingAccept();
  mocks.auth.session = { user: { id: "account-b" }, access_token: "token-b" };
  mocks.auth.generation = 2;
  await act(async () => pending.resolve(accepted));
  expect(mocks.push).not.toHaveBeenCalled();
  view.rerender(flow());
  expect(screen.getByRole("button", { name: /pay deposit/i })).toBeEnabled();
});

it("does not update A's error when signout publishes before React rerenders", async () => {
  const view = renderFlow();
  const pending = await startPendingAccept();
  mocks.auth.session = null;
  mocks.auth.generation = 2;
  await act(async () => pending.reject(new Error("A failed")));
  expect(screen.queryByText(/could not start the deposit/i)).not.toBeInTheDocument();
  view.rerender(flow());
  expect(screen.queryByRole("button", { name: /pay deposit/i })).not.toBeInTheDocument();
});

it("does not start an accept from stale UI after auth publishes a new account", async () => {
  renderFlow();
  mocks.auth.session = { user: { id: "account-b" }, access_token: "token-b" };
  mocks.auth.generation = 2;
  await userEvent.setup().click(screen.getByRole("button", { name: /pay deposit/i }));
  expect(mocks.request).not.toHaveBeenCalled();
});

it("discards acceptance completion from an earlier auth generation", async () => {
  const view = renderFlow();
  const pending = await startPendingAccept();
  mocks.auth.generation = 2;
  view.rerender(flow());
  await act(async () => pending.resolve(accepted));
  expect(mocks.push).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: /pay deposit/i })).toBeEnabled();
});

it("does not navigate when acceptance completes after signout", async () => {
  const view = renderFlow();
  const pending = await startPendingAccept();
  mocks.auth.session = null;
  mocks.auth.generation = 2;
  view.rerender(flow());
  await act(async () => pending.resolve(accepted));
  expect(mocks.push).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: /pay deposit/i })).not.toBeInTheDocument();
});

it.each([
  ["job-b", "quote-a"],
  ["job-a", "quote-b"],
])("does not navigate to old checkout when route changes to %s/%s", async (jobId, quoteId) => {
  const view = renderFlow();
  const pending = await startPendingAccept();
  view.rerender(flow(jobId, quoteId));
  await act(async () => pending.resolve(accepted));
  expect(mocks.push).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: /pay deposit/i })).toBeEnabled();
});

it("keeps a pending accept across same-account token refresh and prevents a repeat click", async () => {
  const view = renderFlow();
  const pending = await startPendingAccept();
  mocks.auth.session = {
    user: { id: "account-a" },
    access_token: "token-a-refreshed",
  };
  view.rerender(flow());
  expect(screen.getByRole("button", { name: /setting up your deposit/i })).toBeDisabled();
  await userEvent.setup().click(screen.getByRole("button", { name: /setting up your deposit/i }));
  expect(mocks.request).toHaveBeenCalledTimes(1);
  await act(async () => pending.resolve(accepted));
  expect(mocks.push).toHaveBeenCalledWith("/en/checkout?session=checkout-a&kind=service_deposit");
});

it("allows retry after a failed accept using the refreshed same-account token", async () => {
  const view = renderFlow();
  mocks.request.mockRejectedValueOnce(new Error("network"));
  await userEvent.setup().click(screen.getByRole("button", { name: /pay deposit/i }));
  await waitFor(() => expect(screen.getByRole("button", { name: /pay deposit/i })).toBeEnabled());
  mocks.auth.session = {
    user: { id: "account-a" },
    access_token: "token-a-refreshed",
  };
  view.rerender(flow());
  mocks.request.mockResolvedValueOnce(accepted);
  await userEvent.setup().click(screen.getByRole("button", { name: /pay deposit/i }));
  await waitFor(() => expect(mocks.push).toHaveBeenCalledTimes(1));
  expect(mocks.request).toHaveBeenCalledTimes(2);
  expect(mocks.getToken?.()).toBe("token-a-refreshed");
});
