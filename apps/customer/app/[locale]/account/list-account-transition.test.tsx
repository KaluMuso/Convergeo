// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
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
const mocks = vi.hoisted(() => ({ refresh: vi.fn(), fetch: vi.fn() }));

vi.mock("../../../lib/customer-session", async () => {
  const { useSyncExternalStore } = await import("react");
  return {
    useSession: () =>
      useSyncExternalStore(
        (listener) => {
          auth.listeners.add(listener);
          return () => {
            auth.listeners.delete(listener);
          };
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
  redirect: (url: string) => {
    throw new Error(`redirect ${url}`);
  },
}));
vi.mock("../../../lib/api-base-url", () => ({
  getApiBaseUrl: () => "https://api.example.test",
}));
vi.mock("next-intl/server", () => ({
  getMessages: async () => ({}),
  setRequestLocale: () => undefined,
}));

import JobsPage from "./jobs/page";
import QuotesPage from "./quotes/page";

const pages = [
  { name: "jobs", Page: JobsPage, privateText: "Private job A", id: "job-A" },
  {
    name: "quotes",
    Page: QuotesPage,
    privateText: "Private quote A",
    id: "thread-A",
  },
] as const;

function payload(kind: "jobs" | "quotes", account: string) {
  if (kind === "jobs") {
    return {
      items: [
        {
          id: `job-${account}`,
          category: "cleaning",
          description: `Private job ${account}`,
          status: "quoted",
          created_at: "2026-10-01T00:00:00Z",
          budget_band_min_ngwee: null,
          budget_band_max_ngwee: null,
        },
      ],
    };
  }
  return {
    items: [
      {
        id: `thread-${account}`,
        listing_id: `listing-${account}`,
        requested_details: `Private quote ${account}`,
        status: "quoted",
        created_at: "2026-10-01T00:00:00Z",
        quote_price_ngwee: 1000,
      },
    ],
  };
}

const originalFetch = globalThis.fetch;
function publishSession() {
  act(() => {
    auth.snapshot = {
      session: auth.session,
      generation: auth.generation,
      loading: auth.loading,
    };
    auth.listeners.forEach((listener) => listener());
  });
}

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  mocks.refresh.mockReset();
  mocks.fetch.mockReset();
  auth.session = { user: { id: "A" }, access_token: "token-A" };
  auth.generation = 1;
  auth.loading = false;
  auth.serverAccount = "A";
  auth.denyB = false;
  auth.snapshot = null;
  auth.listeners.clear();
});

function mockFetch() {
  globalThis.fetch = mocks.fetch.mockImplementation(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const account = String(new Headers(init?.headers).get("Authorization")).endsWith("token-B")
        ? "B"
        : "A";
      if (account === "B" && auth.denyB) return new Response(null, { status: 403 });
      const kind = String(input).endsWith("/jobs") ? "jobs" : "quotes";
      return new Response(JSON.stringify(payload(kind, account)), {
        status: 200,
      });
    },
  ) as typeof fetch;
}

for (const { name, Page, privateText, id } of pages) {
  const params = Promise.resolve({ locale: "en" });

  it(`${name}: preserves authenticated server HTML and no-store API fetch`, async () => {
    mockFetch();
    publishSession();
    const html = renderToString(await Page({ params }));
    expect(html).toContain(privateText);
    expect(html).toContain(id);
    expect(mocks.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it(`${name}: hides A rows and action IDs on B switch, then shows only fresh B data`, async () => {
    mockFetch();
    publishSession();
    const oldTree = await Page({ params });
    const view = render(oldTree);
    expect(screen.getByText(privateText)).toBeInTheDocument();
    expect(view.container.querySelector(`a[href$="${id}"]`)).not.toBeNull();

    auth.session = null;
    auth.loading = true;
    auth.generation = 2;
    publishSession();
    expect(screen.queryByText(privateText)).not.toBeInTheDocument();
    expect(view.container.querySelector(`a[href$="${id}"]`)).toBeNull();

    auth.session = { user: { id: "B" }, access_token: "token-B" };
    auth.loading = false;
    auth.serverAccount = "B";
    publishSession();
    expect(screen.queryByText(privateText)).not.toBeInTheDocument();
    expect(view.container.querySelector(`a[href$="${id}"]`)).toBeNull();
    expect(mocks.refresh).toHaveBeenCalled();
    view.rerender(await Page({ params }));
    expect(screen.getByText(`Private ${name === "jobs" ? "job" : "quote"} B`)).toBeInTheDocument();
  });

  it(`${name}: hides A on signout and does not reveal A after a denied B load`, async () => {
    mockFetch();
    publishSession();
    const oldTree = await Page({ params });
    const view = render(oldTree);
    expect(screen.getByText(privateText)).toBeInTheDocument();
    auth.session = null;
    auth.generation = 2;
    publishSession();
    expect(screen.queryByText(privateText)).not.toBeInTheDocument();
    auth.session = { user: { id: "B" }, access_token: "token-B" };
    auth.generation = 3;
    auth.serverAccount = "B";
    auth.denyB = true;
    publishSession();
    view.rerender(await Page({ params }));
    expect(screen.queryByText(privateText)).not.toBeInTheDocument();
    expect(view.container.querySelector(`a[href$="${id}"]`)).toBeNull();
  });

  it(`${name}: keeps A through token refresh but hides a late A payload after B`, async () => {
    mockFetch();
    publishSession();
    const view = render(await Page({ params }));
    expect(screen.getByText(privateText)).toBeInTheDocument();
    auth.session = { user: { id: "A" }, access_token: "token-A-new" };
    publishSession();
    view.rerender(await Page({ params }));
    expect(screen.getByText(privateText)).toBeInTheDocument();
    expect(mocks.refresh).not.toHaveBeenCalled();

    const staleA = await Page({ params });
    auth.session = { user: { id: "B" }, access_token: "token-B" };
    auth.generation = 2;
    auth.serverAccount = "B";
    publishSession();
    view.rerender(await Page({ params }));
    expect(screen.getByText(`Private ${name === "jobs" ? "job" : "quote"} B`)).toBeInTheDocument();
    view.rerender(staleA);
    expect(screen.queryByText(privateText)).not.toBeInTheDocument();
    expect(view.container.querySelector(`a[href$="${id}"]`)).toBeNull();
    await waitFor(() => expect(mocks.refresh).toHaveBeenCalled());
  });

  it(`${name}: hides a stale A server payload on a fresh mount after B or signout`, async () => {
    mockFetch();
    publishSession();
    const staleA = await Page({ params });

    auth.session = { user: { id: "B" }, access_token: "token-B" };
    auth.generation = 2;
    publishSession();
    const view = render(staleA);
    expect(screen.queryByText(privateText)).not.toBeInTheDocument();
    expect(view.container.querySelector(`a[href$="${id}"]`)).toBeNull();

    view.unmount();
    auth.session = null;
    auth.generation = 3;
    publishSession();
    const signedOut = render(staleA);
    expect(screen.queryByText(privateText)).not.toBeInTheDocument();
    expect(signedOut.container.querySelector(`a[href$="${id}"]`)).toBeNull();
  });
}
