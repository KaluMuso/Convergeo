// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  createClient: vi.fn(),
  apiOrigin: "https://api.example.invalid" as string | undefined,
  auth: {
    loading: false,
    session: { access_token: "local-test-token", user: { phone: "+260971234567" } } as {
      access_token: string;
      user: { phone: string };
    } | null,
  },
  push: vi.fn(),
  replace: vi.fn(),
  network: vi.fn(() => {
    throw new Error("WP10H regression forbids real network requests");
  }),
}));

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => mocks.auth,
}));

vi.mock("@vergeo/config", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@vergeo/config")>()),
  createApiClient: (...args: unknown[]) => {
    mocks.createClient(...args);
    return { request: mocks.request };
  },
}));

vi.mock("../../../../../lib/api-base-url", () => ({
  getApiBaseUrl: () => mocks.apiOrigin,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push, replace: mocks.replace, refresh: vi.fn() }),
}));

vi.mock("next-intl/server", () => ({
  getMessages: async () => ({}),
  setRequestLocale: vi.fn(),
  getRequestConfig: (factory: unknown) => factory,
}));

// The route builds label templates without ICU variables. Raw catalogue labels
// isolate that unrelated formatting behavior while retaining the actual route.
vi.mock("next-intl", () => ({
  createTranslator: ({
    messages,
    namespace,
  }: {
    messages: Record<string, unknown>;
    namespace: string;
  }) => {
    const translate = (key: string, values?: Record<string, string>) => {
      const raw = key.split(".").reduce<unknown>((value, part) => {
        return value && typeof value === "object"
          ? (value as Record<string, unknown>)[part]
          : undefined;
      }, messages[namespace]);
      return typeof raw === "string"
        ? raw.replace(/\{(\w+)\}/g, (match, key: string) => values?.[key] ?? match)
        : raw;
    };
    translate.raw = (key: string) => translate(key);
    return translate;
  },
}));

// Keep this regression on route-to-session handoff; contact/OTP has its own tests.
vi.mock("../_components/step-contact", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../_components/step-contact")>()),
  StepContact: () => null,
}));

const { ApiError } = await import("@vergeo/config");
const { default: CheckoutPage } = await import("../page");

beforeEach(() => {
  vi.stubGlobal("fetch", mocks.network);
  mocks.request.mockReset();
  mocks.apiOrigin = "https://api.example.invalid";
  // An empty product basket is a valid state after either existing-group caller.
  // Stop subsequent requests from resolving so the baseline's retry loop cannot
  // obscure its first wrong request/navigation or create an unbounded test loop.
  mocks.auth.loading = false;
  mocks.auth.session = { access_token: "local-test-token", user: { phone: "+260971234567" } };
  let productAttempts = 0;
  mocks.request.mockImplementation((path: string, options: { method: string }) => {
    if (path === "/checkout/session" && options.method === "POST") {
      return productAttempts++ === 0
        ? Promise.reject(new ApiError("checkout.cart_empty", "Empty product cart"))
        : new Promise(() => {});
    }
    if (path.startsWith("/checkout/session/") && options.method === "GET") {
      return Promise.resolve(status(path.slice("/checkout/session/".length)));
    }
    throw new Error(`Forbidden endpoint: ${path}`);
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/");
});

const firstId = "11111111-1111-4111-8111-111111111111";
const secondId = "22222222-2222-4222-8222-222222222222";
type Query = Record<string, string | string[] | undefined>;
function status(id = firstId, changes: Record<string, unknown> = {}) {
  return {
    session_id: id,
    status: "pending",
    expired: false,
    expires_at: "2099-01-01T00:00:00Z",
    ...changes,
  };
}
async function checkoutElement(query: Query, locale = "en") {
  return CheckoutPage({
    params: Promise.resolve({ locale }),
    searchParams: Promise.resolve(query),
  });
}
async function visitCheckout(query: Query, locale = "en") {
  return render(await checkoutElement(query, locale));
}
function expectReadOnly() {
  expect(
    mocks.request.mock.calls.every(
      ([path, options]) => /^\/checkout\/session\/[^/]+$/.test(path) && options.method === "GET",
    ),
  ).toBe(true);
  expect(mocks.push).not.toHaveBeenCalled();
  expect(mocks.replace).not.toHaveBeenCalled();
  expect(mocks.network).not.toHaveBeenCalled();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
}

describe("WP10H existing checkout group handoff", () => {
  const handoffs: Array<{ caller: string; query: Record<string, string> }> = [
    {
      caller: "service deposit session parameter",
      query: {
        session: "11111111-1111-4111-8111-111111111111",
        kind: "service_deposit",
      },
    },
    {
      caller: "paid event group parameter",
      query: { group: "22222222-2222-4222-8222-222222222222" },
    },
  ];

  it.each(handoffs)("does not create a product session for $caller", async ({ query }) => {
    await visitCheckout(query);
    await screen.findByText("Status: Pending");
    expect(mocks.request).toHaveBeenCalledWith(
      `/checkout/session/${query.session ?? query.group}`,
      { method: "GET" },
    );
    expect(screen.getByText("Payment: Unavailable")).toBeInTheDocument();
    expectReadOnly();
    expect(mocks.request).not.toHaveBeenCalledWith("/checkout/session", { method: "POST" });
    expect(mocks.push).not.toHaveBeenCalledWith("/en/cart");
    expect(mocks.network).not.toHaveBeenCalled();
  });

  it("preserves the empty-product-cart redirect when no handoff is supplied", async () => {
    await visitCheckout({});
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/en/cart"));
    expect(mocks.request).toHaveBeenCalledWith("/checkout/session", { method: "POST" });
    expect(mocks.network).not.toHaveBeenCalled();
  });

  it.each<Query>([
    { session: "" },
    { group: " " },
    { session: "not-a-uuid" },
    { group: "../orders" },
    { session: undefined },
    { group: [] },
    { session: [firstId] },
    { group: [firstId, firstId] },
    { session: firstId, group: secondId },
    { session: firstId, group: firstId },
  ])("fails closed for invalid or duplicate query %j", async (query) => {
    await visitCheckout(query);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    expect(mocks.request).not.toHaveBeenCalled();
    expectReadOnly();
  });

  it("preserves the supplied identifier and locale", async () => {
    const id = "ABCDEF12-ABCD-4ABC-8ABC-ABCDEF123456";
    await visitCheckout({ group: id }, "fr");
    await waitFor(() =>
      expect(mocks.request).toHaveBeenCalledWith(`/checkout/session/${id}`, { method: "GET" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Statut : En attente"),
    );
    expect(screen.getByRole("status").textContent).toBe("Statut : En attente");
    expect(screen.getByText("Paiement: Indisponible")).toBeInTheDocument();
    expect(screen.queryByText("Payment: Unavailable")).not.toBeInTheDocument();
    expectReadOnly();
  });

  it("waits for authentication and fails closed for an anonymous user", async () => {
    mocks.auth.loading = true;
    mocks.auth.session = null;
    const view = await visitCheckout({ session: firstId });
    expect(screen.getByRole("status")).toHaveTextContent("Please wait");
    expect(mocks.request).not.toHaveBeenCalled();
    mocks.auth.loading = false;
    view.rerender(await checkoutElement({ session: firstId }));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(mocks.request).not.toHaveBeenCalled();
    expectReadOnly();
  });

  it.each([401, 403, 404, 500])(
    "uses a generic error for denied/foreign/error response %s",
    async (code) => {
      mocks.request.mockRejectedValue(new Error(`HTTP ${code}: private detail`));
      await visitCheckout({ group: firstId });
      expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
      expect(screen.queryByText(/private detail/)).not.toBeInTheDocument();
      expectReadOnly();
    },
  );

  it.each([
    { expired: true },
    { status: "expired" },
    { status: "abandoned" },
    { expires_at: "2000-01-01T00:00:00Z" },
  ])("shows expiry without releasing or mutating the group %j", async (changes) => {
    mocks.request.mockResolvedValue(status(firstId, changes));
    await visitCheckout({ session: firstId });
    await screen.findByText("Reservation expired");
    expectReadOnly();
  });

  it.each([
    null,
    status(secondId),
    status(firstId, { status: "paid" }),
    status(firstId, { expired: "false" }),
    status(firstId, { expires_at: "invalid" }),
  ])("rejects malformed or mismatched server status %j", async (response) => {
    mocks.request.mockResolvedValue(response);
    await visitCheckout({ session: firstId });
    await screen.findByRole("alert");
    expectReadOnly();
  });

  it("renders a completed server status without claiming payment or navigating", async () => {
    mocks.request.mockResolvedValue(status(firstId, { status: "completed" }));
    await visitCheckout({ group: firstId });
    await screen.findByText("Status: Completed");
    expectReadOnly();
  });

  it("does not re-fetch or mutate on repeated renders or alias changes", async () => {
    const view = await visitCheckout({ session: firstId });
    await screen.findByText("Status: Pending");
    view.rerender(await checkoutElement({ session: firstId }));
    view.rerender(await checkoutElement({ group: firstId }));
    expect(mocks.request).toHaveBeenCalledTimes(1);
    expectReadOnly();
  });

  it("ignores a stale response after query changes", async () => {
    let resolveOld!: (value: ReturnType<typeof status>) => void;
    mocks.request.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve;
        }),
    );
    const view = await visitCheckout({ session: firstId });
    expect(screen.getByRole("status")).toHaveTextContent("Please wait");
    view.rerender(await checkoutElement({ group: secondId }));
    await screen.findByText("Status: Pending");
    await act(async () => {
      resolveOld(status(firstId, { status: "completed" }));
    });
    expect(screen.queryByText("Status: Completed")).not.toBeInTheDocument();
    expect(mocks.request).toHaveBeenCalledTimes(2);
    view.rerender(await checkoutElement({ group: "" }));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("Status: Pending")).not.toBeInTheDocument();
    expectReadOnly();
  });

  it("hides an earlier user's status on logout and token change", async () => {
    const view = await visitCheckout({ group: firstId });
    await screen.findByText("Status: Pending");
    mocks.auth.session = null;
    view.rerender(await checkoutElement({ group: firstId }));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("Status: Pending")).not.toBeInTheDocument();
    mocks.auth.session = { access_token: "another-local-token", user: { phone: "+260971234567" } };
    mocks.request.mockRejectedValue(new Error("HTTP 404"));
    view.rerender(await checkoutElement({ group: firstId }));
    expect(screen.queryByText("Status: Pending")).not.toBeInTheDocument();
    await screen.findByRole("alert");
    expect(mocks.request).toHaveBeenCalledTimes(2);
    expectReadOnly();
  });

  it("localizes completed and expired French group states", async () => {
    mocks.request.mockResolvedValue(status(firstId, { status: "completed" }));
    const view = await visitCheckout({ group: firstId }, "fr");
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Statut : Terminée"));
    expect(screen.getByText("Paiement: Indisponible")).toBeInTheDocument();
    mocks.request.mockResolvedValue(status(secondId, { expired: true }));
    view.rerender(await checkoutElement({ group: secondId }, "fr"));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Réservation expirée"));
    expectReadOnly();
  });

  it.each([undefined, "", " "])(
    "rejects missing or empty API origin %j before client creation",
    async (origin) => {
      mocks.apiOrigin = origin;
      await visitCheckout({ group: firstId });
      expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
      expect(mocks.createClient).not.toHaveBeenCalled();
      expect(mocks.request).not.toHaveBeenCalled();
      expectReadOnly();
    },
  );

  it("expires an idle pending view at the server deadline without a request or mutation", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2030-01-01T00:00:00Z"));
    mocks.request.mockResolvedValue(status(firstId, { expires_at: "2030-01-01T00:00:01Z" }));
    await act(async () => {
      await visitCheckout({ session: firstId });
    });
    expect(screen.getByRole("status").textContent).toBe("Status: Pending");
    expect(vi.getTimerCount()).toBe(1);
    await act(async () => {
      vi.advanceTimersByTime(999);
    });
    expect(screen.getByRole("status").textContent).toBe("Status: Pending");
    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.getByRole("status").textContent).toBe("Reservation expired");
    expect(vi.getTimerCount()).toBe(0);
    expect(mocks.request).toHaveBeenCalledTimes(1);
    expectReadOnly();
  });

  it("cancels the expiry timer on query/auth changes and unmount", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2030-01-01T00:00:00Z"));
    mocks.request.mockImplementation((path: string) =>
      Promise.resolve(
        status(path.slice("/checkout/session/".length), {
          expires_at: path.endsWith(firstId) ? "2030-01-01T00:00:01Z" : "2030-01-01T00:00:10Z",
        }),
      ),
    );
    let view!: Awaited<ReturnType<typeof visitCheckout>>;
    await act(async () => {
      view = await visitCheckout({ group: firstId });
    });
    expect(vi.getTimerCount()).toBe(1);
    await act(async () => {
      view.rerender(await checkoutElement({ group: secondId }));
    });
    expect(vi.getTimerCount()).toBe(1);
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByRole("status").textContent).toBe("Status: Pending");
    mocks.auth.loading = true;
    await act(async () => {
      view.rerender(await checkoutElement({ group: secondId }));
    });
    expect(vi.getTimerCount()).toBe(0);
    mocks.auth.loading = false;
    mocks.auth.session = null;
    await act(async () => {
      view.rerender(await checkoutElement({ group: secondId }));
    });
    expect(vi.getTimerCount()).toBe(0);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    mocks.auth.session = { access_token: "new-local-token", user: { phone: "+260971234567" } };
    await act(async () => {
      view.rerender(await checkoutElement({ group: secondId }));
    });
    expect(vi.getTimerCount()).toBe(1);
    expect(mocks.request).toHaveBeenCalledTimes(3);
    expectReadOnly();
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("keeps the #752 public contact intro in ordinary checkout SSR only", async () => {
    mocks.auth.loading = true;
    mocks.auth.session = null;
    const ordinary = new DOMParser().parseFromString(
      renderToString(await checkoutElement({}, "fr")),
      "text/html",
    );
    expect(ordinary.querySelector("h2")?.textContent).toBe("Vos coordonnées");
    expect(ordinary.body.textContent).toContain(
      "Nous les utiliserons pour envoyer les mises à jour de commande sur WhatsApp ou SMS.",
    );
    expect(ordinary.querySelector('[data-testid="checkout-loading-skeleton"]')).not.toBeNull();
    expect(ordinary.querySelector("input, form, button")).toBeNull();
    const handoff = new DOMParser().parseFromString(
      renderToString(await checkoutElement({ group: firstId }, "fr")),
      "text/html",
    );
    expect(handoff.querySelector('[role="status"]')?.textContent).toBe("Veuillez patienter…");
    expect(handoff.querySelector("h2, input, form, button")).toBeNull();
    expect(handoff.querySelector('[data-testid="checkout-loading-skeleton"]')).toBeNull();
    expect(mocks.createClient).not.toHaveBeenCalled();
    expect(mocks.request).not.toHaveBeenCalled();
    expectReadOnly();
  });

  it("switches from handoff to ordinary loading without initializing a product cart early", async () => {
    const view = await visitCheckout({ group: firstId });
    await screen.findByText("Status: Pending");
    mocks.auth.loading = true;
    mocks.auth.session = null;
    view.rerender(await checkoutElement({}, "fr"));
    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe("Vos coordonnées");
    expect(screen.getByTestId("checkout-loading-skeleton")).toBeInTheDocument();
    expect(mocks.request).toHaveBeenCalledTimes(1);
    expect(mocks.request).not.toHaveBeenCalledWith("/checkout/session", { method: "POST" });
    view.rerender(await checkoutElement({ session: secondId }, "fr"));
    expect(screen.queryByRole("heading", { level: 2 })).not.toBeInTheDocument();
    expect(screen.queryByTestId("checkout-loading-skeleton")).not.toBeInTheDocument();
    expect(screen.getByRole("status").textContent).toBe("Veuillez patienter…");
    expect(mocks.request).toHaveBeenCalledTimes(1);
    expectReadOnly();
  });
});
