// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { Suspense } from "react";
import { afterEach, expect, it, vi } from "vitest";

import servicesMessages from "../../../../../../../packages/i18n/messages/en/services.json";

const state = vi.hoisted(() => ({
  session: { access_token: "token-a", user: { id: "account-a" } } as {
    access_token: string;
    user: { id: string };
  } | null,
  generation: 1,
  loading: false,
}));
const mocks = vi.hoisted(() => ({ request: vi.fn(), push: vi.fn() }));

vi.mock("../../../../../lib/customer-session", () => ({
  useSession: () => ({ ...state }),
  customerAuth: { snapshot: () => ({ ...state }) },
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
}));
vi.mock("@vergeo/config", () => {
  class ApiError extends Error {
    status: number;
    constructor(_code: string, message: string, options: { status: number }) {
      super(message);
      this.status = options.status;
    }
  }
  return {
    ApiError,
    createApiClient: ({ getToken }: { getToken: () => string | null }) => ({
      request: (path: string, options?: unknown) => mocks.request(getToken(), path, options),
    }),
  };
});
vi.mock("./_components/complete-confirm", () => ({
  CompleteConfirm: () => null,
}));
vi.mock("./_components/service-review-form", () => ({
  ServiceReviewForm: () => null,
}));

import Page from "./page";

const quoted = {
  id: "quote-a",
  amount_ngwee: 120_000,
  message: "Private message A",
  status: "submitted",
  expires_at: null,
  created_at: "2026-10-01T00:00:00Z",
  provider: {
    vendor_id: "vendor-a",
    slug: "a",
    display_name: "Provider A",
    preferred_badge: false,
    rating_avg: null,
    rating_count: 0,
    response_time_tier: null,
  },
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

async function mount(id = "job-a") {
  let currentId = id;
  let params = Promise.resolve({ locale: "en", id });
  const wrap = () => (
    <Suspense fallback={<p>Loading route</p>}>
      <NextIntlClientProvider
        locale="en"
        messages={{ services: servicesMessages }}
        onError={() => {}}
      >
        <Page params={params} />
      </NextIntlClientProvider>
    </Suspense>
  );
  let view!: ReturnType<typeof render>;
  await act(async () => {
    view = render(wrap());
    await params;
  });
  return async (nextId = currentId) => {
    if (nextId !== currentId) {
      currentId = nextId;
      params = Promise.resolve({ locale: "en", id: nextId });
    }
    await act(async () => {
      view.rerender(wrap());
      await params;
    });
  };
}

afterEach(() => {
  cleanup();
  mocks.request.mockReset();
  mocks.push.mockReset();
  state.session = { access_token: "token-a", user: { id: "account-a" } };
  state.generation = 1;
  state.loading = false;
});

it("keeps a pending accept mounted through a same-account token refresh", async () => {
  const accept = deferred<{ checkout_group_id: string }>();
  mocks.request.mockImplementation((_token: string, path: string) => {
    if (path.endsWith("/accept")) return accept.promise;
    if (path.endsWith("/quotes")) return { items: [quoted], view: "owner" };
    return { id: "job-a", status: "quoted" };
  });
  const rerender = await mount();
  await screen.findByText("Provider A");
  await userEvent.setup().click(screen.getByRole("button", { name: /pay deposit/i }));
  await waitFor(() =>
    expect(mocks.request).toHaveBeenCalledWith(
      "token-a",
      "/jobs/job-a/quotes/quote-a/accept",
      expect.anything(),
    ),
  );

  state.session = {
    access_token: "token-refreshed",
    user: { id: "account-a" },
  };
  await rerender();
  expect(screen.getByRole("button", { name: /setting up your deposit/i })).toBeDisabled();
  await act(async () => accept.resolve({ checkout_group_id: "checkout-a" }));
  expect(mocks.push).toHaveBeenCalledWith("/en/checkout?session=checkout-a&kind=service_deposit");
});

it("does not replace a pending accept when an earlier refresh returns accepted", async () => {
  const refresh = deferred<{ items: (typeof quoted)[]; view: string }>();
  const accept = deferred<{ checkout_group_id: string }>();
  mocks.request.mockImplementation((token: string, path: string) => {
    if (path.endsWith("/accept")) return accept.promise;
    if (path.endsWith("/quotes"))
      return token === "token-refreshed" ? refresh.promise : { items: [quoted], view: "owner" };
    return { id: "job-a", status: "quoted" };
  });
  const rerender = await mount();
  await screen.findByText("Provider A");
  state.session = {
    access_token: "token-refreshed",
    user: { id: "account-a" },
  };
  await rerender();
  await waitFor(() =>
    expect(mocks.request).toHaveBeenCalledWith("token-refreshed", "/jobs/job-a/quotes", undefined),
  );
  await userEvent.setup().click(screen.getByRole("button", { name: /pay deposit/i }));
  await act(async () =>
    refresh.resolve({
      items: [{ ...quoted, status: "accepted" }],
      view: "owner",
    }),
  );
  expect(screen.getByRole("button", { name: /setting up your deposit/i })).toBeDisabled();
  await act(async () => accept.resolve({ checkout_group_id: "checkout-a" }));
  expect(mocks.push).toHaveBeenCalledWith("/en/checkout?session=checkout-a&kind=service_deposit");
});

it("refreshes with the latest same-account token after a failed accept", async () => {
  const accept = deferred<{ checkout_group_id: string }>();
  mocks.request.mockImplementation((_token: string, path: string) => {
    if (path.endsWith("/accept")) return accept.promise;
    if (path.endsWith("/quotes")) return { items: [quoted], view: "owner" };
    return { id: "job-a", status: "quoted" };
  });
  const rerender = await mount();
  await screen.findByText("Provider A");
  await userEvent.setup().click(screen.getByRole("button", { name: /pay deposit/i }));
  state.session = {
    access_token: "token-refreshed",
    user: { id: "account-a" },
  };
  await rerender();
  await act(async () => accept.reject(new Error("network")));
  await waitFor(() =>
    expect(mocks.request).toHaveBeenCalledWith("token-refreshed", "/jobs/job-a/quotes", undefined),
  );
  expect(screen.getByRole("button", { name: /pay deposit/i })).toBeEnabled();
  expect(mocks.push).not.toHaveBeenCalled();
});

it("does not navigate from A's acceptance after B receives 403", async () => {
  const accept = deferred<{ checkout_group_id: string }>();
  const { ApiError } = await import("@vergeo/config");
  mocks.request.mockImplementation((token: string, path: string) => {
    if (path.endsWith("/accept")) return accept.promise;
    if (path.endsWith("/quotes"))
      return token === "token-b"
        ? Promise.reject(new ApiError("forbidden", "Forbidden", { status: 403 }))
        : { items: [quoted], view: "owner" };
    return { id: "job-a", status: "quoted" };
  });
  const rerender = await mount();
  await screen.findByText("Provider A");
  await userEvent.setup().click(screen.getByRole("button", { name: /pay deposit/i }));
  state.session = { access_token: "token-b", user: { id: "account-b" } };
  state.generation++;
  await rerender();
  expect(screen.queryByText("Provider A")).not.toBeInTheDocument();
  expect(await screen.findByText(servicesMessages.quotes.errors.forbidden)).toBeInTheDocument();
  await act(async () => accept.resolve({ checkout_group_id: "checkout-a" }));
  expect(mocks.push).not.toHaveBeenCalled();
  expect(screen.queryByText("Private message A")).not.toBeInTheDocument();
});

it("keeps a pending accept mounted when an earlier refresh fails transiently", async () => {
  const refresh = deferred<{ items: (typeof quoted)[]; view: string }>();
  const accept = deferred<{ checkout_group_id: string }>();
  mocks.request.mockImplementation((token: string, path: string) => {
    if (path.endsWith("/accept")) return accept.promise;
    if (path.endsWith("/quotes"))
      return token === "token-refreshed" ? refresh.promise : { items: [quoted], view: "owner" };
    return { id: "job-a", status: "quoted" };
  });
  const rerender = await mount();
  await screen.findByText("Provider A");
  state.session = {
    access_token: "token-refreshed",
    user: { id: "account-a" },
  };
  await rerender();
  await waitFor(() =>
    expect(mocks.request).toHaveBeenCalledWith("token-refreshed", "/jobs/job-a/quotes", undefined),
  );
  await userEvent.setup().click(screen.getByRole("button", { name: /pay deposit/i }));
  await act(async () => refresh.reject(new Error("transient refresh failure")));
  expect(screen.getByRole("button", { name: /setting up your deposit/i })).toBeDisabled();
  await act(async () => accept.resolve({ checkout_group_id: "checkout-a" }));
  expect(mocks.push).toHaveBeenCalledWith("/en/checkout?session=checkout-a&kind=service_deposit");
});

it.each([401, 403])(
  "clears private data when a refresh denies access with %s during acceptance",
  async (status) => {
    const refresh = deferred<{ items: (typeof quoted)[]; view: string }>();
    const accept = deferred<{ checkout_group_id: string }>();
    const { ApiError } = await import("@vergeo/config");
    mocks.request.mockImplementation((token: string, path: string) => {
      if (path.endsWith("/accept")) return accept.promise;
      if (path.endsWith("/quotes"))
        return token === "token-refreshed" ? refresh.promise : { items: [quoted], view: "owner" };
      return { id: "job-a", status: "quoted" };
    });
    const rerender = await mount();
    await screen.findByText("Provider A");
    state.session = {
      access_token: "token-refreshed",
      user: { id: "account-a" },
    };
    await rerender();
    await userEvent.setup().click(screen.getByRole("button", { name: /pay deposit/i }));
    await act(async () => refresh.reject(new ApiError("denied", "Denied", { status })));
    expect(screen.queryByText("Provider A")).not.toBeInTheDocument();
    expect(screen.queryByText("Private message A")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /deposit/i })).not.toBeInTheDocument();
    await act(async () => accept.resolve({ checkout_group_id: "checkout-a" }));
    expect(mocks.push).not.toHaveBeenCalled();
  },
);

it("does not navigate from A's acceptance after route navigation to job B", async () => {
  const accept = deferred<{ checkout_group_id: string }>();
  mocks.request.mockImplementation((_token: string, path: string) => {
    if (path.endsWith("/accept")) return accept.promise;
    if (path.endsWith("/quotes"))
      return path.includes("job-b")
        ? {
            items: [
              {
                ...quoted,
                id: "quote-b",
                message: "Private message B",
                provider: { ...quoted.provider, display_name: "Provider B" },
              },
            ],
            view: "owner",
          }
        : { items: [quoted], view: "owner" };
    return { id: path.includes("job-b") ? "job-b" : "job-a", status: "quoted" };
  });
  const rerender = await mount();
  await screen.findByText("Provider A");
  await userEvent.setup().click(screen.getByRole("button", { name: /pay deposit/i }));
  await rerender("job-b");
  expect(await screen.findByText("Provider B")).toBeInTheDocument();
  expect(screen.queryByText("Private message A")).not.toBeInTheDocument();
  await act(async () => accept.resolve({ checkout_group_id: "checkout-a" }));
  expect(mocks.push).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: /pay deposit/i })).toBeEnabled();
});
