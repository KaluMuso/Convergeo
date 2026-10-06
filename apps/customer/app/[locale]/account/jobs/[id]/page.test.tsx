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
  error: null,
}));
const requests = vi.hoisted(() => vi.fn());

vi.mock("../../../../../lib/customer-session", () => ({
  useSession: () => ({ ...state }),
  customerAuth: { snapshot: () => ({ ...state }) },
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
      request: (path: string, options?: unknown) => requests(getToken(), path, options),
    }),
  };
});
vi.mock("./_components/accept-flow", () => ({
  DEFAULT_DEPOSIT_PCT: 50,
  previewDepositNgwee: (amount: number) => amount / 2,
  AcceptFlow: ({ quoteId }: { quoteId: string }) => <button>Accept {quoteId}</button>,
}));
vi.mock("./_components/complete-confirm", () => ({
  CompleteConfirm: () => null,
}));
vi.mock("./_components/service-review-form", () => ({
  ServiceReviewForm: ({ jobId }: { jobId: string }) => <button>Review {jobId}</button>,
}));

import Page from "./page";

const quote = (name: string) => ({
  id: `quote-${name}`,
  amount_ngwee: 10_000,
  message: `Private message ${name}`,
  status: "submitted",
  expires_at: null,
  created_at: "2026-10-01T00:00:00Z",
  provider: {
    vendor_id: `vendor-${name}`,
    slug: name,
    display_name: `Provider ${name}`,
    preferred_badge: false,
    rating_avg: null,
    rating_count: 0,
    response_time_tier: null,
  },
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

async function mount(id = "job-a") {
  const params = Promise.resolve({ locale: "en", id });
  const wrap = (nextParams: Promise<{ locale: string; id: string }>) => (
    <Suspense fallback={<p>Loading route</p>}>
      <NextIntlClientProvider
        locale="en"
        messages={{
          services: {
            quotes: servicesMessages.quotes,
            badges: servicesMessages.badges,
          },
        }}
      >
        <Page params={nextParams} />
      </NextIntlClientProvider>
    </Suspense>
  );
  let view!: ReturnType<typeof render>;
  await act(async () => {
    view = render(wrap(params));
    await params;
  });
  return {
    rerender: async (nextId = id) => {
      const nextParams = Promise.resolve({ locale: "en", id: nextId });
      await act(async () => {
        view.rerender(wrap(nextParams));
        await nextParams;
      });
    },
  };
}

afterEach(() => {
  cleanup();
  requests.mockReset();
  state.session = { access_token: "token-a", user: { id: "account-a" } };
  state.generation = 1;
  state.loading = false;
});

it("clears account A's quote and actions when account B receives 403", async () => {
  const forbidden = deferred<never>();
  requests.mockImplementation(async (token: string, path: string) => {
    if (token === "token-b" && path.endsWith("/quotes")) return forbidden.promise;
    return path.endsWith("/quotes")
      ? { items: [quote("A")], view: "owner" }
      : { id: "job-a", status: "quoted" };
  });
  const view = await mount();
  expect(await screen.findByText("Provider A")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Accept quote-A" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: servicesMessages.quotes.decline.open }));
  expect(
    screen.getByRole("button", {
      name: servicesMessages.quotes.decline.submit,
    }),
  ).toBeInTheDocument();

  state.session = { access_token: "token-b", user: { id: "account-b" } };
  state.generation++;
  await view.rerender();
  expect(screen.queryByText("Provider A")).not.toBeInTheDocument();
  const { ApiError } = await import("@vergeo/config");
  await act(async () => forbidden.reject(new ApiError("forbidden", "Forbidden", { status: 403 })));
  expect(await screen.findByText(servicesMessages.quotes.errors.forbidden)).toBeInTheDocument();
  expect(screen.queryByText("Provider A")).not.toBeInTheDocument();
  expect(screen.queryByText("Private message A")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Accept quote-A" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Review job-a" })).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", {
      name: servicesMessages.quotes.decline.submit,
    }),
  ).not.toBeInTheDocument();
});

it.each(["success", "error"])(
  "ignores a pending old-account %s after signout and a new sign-in",
  async (result) => {
    const oldQuotes = deferred<{
      items: ReturnType<typeof quote>[];
      view: string;
    }>();
    const newQuotes = deferred<{
      items: ReturnType<typeof quote>[];
      view: string;
    }>();
    requests.mockImplementation((token: string, path: string) => {
      if (!path.endsWith("/quotes")) return Promise.resolve({ id: "job-a", status: "quoted" });
      return token === "token-a" ? oldQuotes.promise : newQuotes.promise;
    });
    const view = await mount();
    await waitFor(() =>
      expect(requests).toHaveBeenCalledWith("token-a", "/jobs/job-a/quotes", undefined),
    );
    state.session = null;
    state.generation++;
    await view.rerender();
    expect(screen.getByText(servicesMessages.quotes.authRequired)).toBeInTheDocument();
    state.session = { access_token: "token-b", user: { id: "account-b" } };
    state.generation++;
    await view.rerender();
    await waitFor(() =>
      expect(requests).toHaveBeenCalledWith("token-b", "/jobs/job-a/quotes", undefined),
    );

    await act(async () => {
      if (result === "success") oldQuotes.resolve({ items: [quote("A")], view: "owner" });
      else oldQuotes.reject(new Error("Old account failed"));
    });
    expect(screen.queryByText("Provider A")).not.toBeInTheDocument();
    expect(screen.queryByText(servicesMessages.quotes.errors.loadFailed)).not.toBeInTheDocument();
    await act(async () => newQuotes.resolve({ items: [quote("B")], view: "owner" }));
    expect(screen.getByText("Provider B")).toBeInTheDocument();
    expect(screen.queryByText("Provider A")).not.toBeInTheDocument();
  },
);

it("keeps the newest response across token refreshes within one account", async () => {
  const oldRefresh = deferred<{
    items: ReturnType<typeof quote>[];
    view: string;
  }>();
  requests.mockImplementation((token: string, path: string) => {
    if (!path.endsWith("/quotes")) return Promise.resolve({ id: "job-a", status: "quoted" });
    if (token === "token-refresh-1") return oldRefresh.promise;
    return Promise.resolve({
      items: [quote(token === "token-refresh-2" ? "Latest" : "Initial")],
      view: "owner",
    });
  });
  const view = await mount();
  expect(await screen.findByText("Provider Initial")).toBeInTheDocument();

  state.session = {
    access_token: "token-refresh-1",
    user: { id: "account-a" },
  };
  await view.rerender();
  await waitFor(() =>
    expect(requests).toHaveBeenCalledWith("token-refresh-1", "/jobs/job-a/quotes", undefined),
  );
  state.session = {
    access_token: "token-refresh-2",
    user: { id: "account-a" },
  };
  await view.rerender();
  expect(await screen.findByText("Provider Latest")).toBeInTheDocument();
  await act(async () => oldRefresh.resolve({ items: [quote("Stale")], view: "owner" }));
  expect(screen.getByText("Provider Latest")).toBeInTheDocument();
  expect(screen.queryByText("Provider Stale")).not.toBeInTheDocument();
});

it("finishes a pending decline after a same-account token refresh", async () => {
  const decline = deferred<void>();
  let declined = false;
  requests.mockImplementation((token: string, path: string) => {
    if (path === "/quotes/quote-A/decline") {
      return decline.promise.then(() => {
        declined = true;
      });
    }
    if (path.endsWith("/quotes")) {
      return Promise.resolve({
        items: [{ ...quote("A"), status: declined ? "declined" : "submitted" }],
        view: "owner",
      });
    }
    return Promise.resolve({ id: "job-a", status: "quoted" });
  });
  const view = await mount();
  expect(await screen.findByText("Provider A")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: servicesMessages.quotes.decline.open }));
  await userEvent.click(
    screen.getByRole("button", {
      name: servicesMessages.quotes.decline.submit,
    }),
  );
  await waitFor(() =>
    expect(requests).toHaveBeenCalledWith("token-a", "/quotes/quote-A/decline", expect.anything()),
  );

  state.session = { access_token: "token-refresh", user: { id: "account-a" } };
  await view.rerender();
  expect(await screen.findByText("Provider A")).toBeInTheDocument();
  await act(async () => decline.resolve());
  await waitFor(() =>
    expect(
      requests.mock.calls.filter(
        ([token, path]) => token === "token-refresh" && path === "/jobs/job-a/quotes",
      ),
    ).toHaveLength(2),
  );
  expect(
    screen.queryByRole("button", {
      name: servicesMessages.quotes.decline.submit,
    }),
  ).not.toBeInTheDocument();
});

it("ignores the old job response after route navigation", async () => {
  const oldQuotes = deferred<{
    items: ReturnType<typeof quote>[];
    view: string;
  }>();
  requests.mockImplementation((token: string, path: string) => {
    if (!path.endsWith("/quotes"))
      return Promise.resolve({ id: path.split("/")[2], status: "quoted" });
    return path.includes("job-a")
      ? oldQuotes.promise
      : Promise.resolve({ items: [quote("B")], view: "owner" });
  });
  const view = await mount();
  await waitFor(() =>
    expect(requests).toHaveBeenCalledWith("token-a", "/jobs/job-a/quotes", undefined),
  );
  await view.rerender("job-b");
  expect(await screen.findByText("Provider B")).toBeInTheDocument();
  await act(async () => oldQuotes.resolve({ items: [quote("A")], view: "owner" }));
  expect(screen.getByText("Provider B")).toBeInTheDocument();
  expect(screen.queryByText("Provider A")).not.toBeInTheDocument();
});
