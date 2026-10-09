// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LOCALES } from "@vergeo/i18n";
import { ThemeProvider } from "@vergeo/ui/src/theme-provider";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import auth from "../../../../../../packages/i18n/messages/en/auth.json";
import common from "../../../../../../packages/i18n/messages/en/common.json";
import vendorMessages from "../../../../../../packages/i18n/messages/en/vendor.json";
import { ResetRequestForm } from "../../../../../customer/app/[locale]/(auth)/_components/reset-request-form";
import { VendorShell } from "../../_components/vendor-shell";

import ConfirmPage, { generateStaticParams as confirmParams } from "./confirm/page";
import RecoveryLayout from "./layout";
import RequestPage, { generateStaticParams as requestParams } from "./page";

// Exercise navigation with its nested catalog; unrelated legacy flat aliases are outside this fixture.
const vendor = { shell: vendorMessages.shell };

const capabilities = {
  home: true,
  orders: true,
  listings: true,
  scan: false,
  returns: true,
  analytics: true,
  services: true,
  events: true,
  rfq: false,
  jobs: false,
  clips: false,
  reviews: true,
  profile: true,
  payouts: false,
  disputes: true,
  intake: false,
};

const mocks = vi.hoisted(() => ({
  client: vi.fn(),
  reset: vi.fn(),
  exchange: vi.fn(),
  update: vi.fn(),
  session: vi.fn(),
  claims: vi.fn(),
  fetch: vi.fn(),
  push: vi.fn(),
  refresh: vi.fn(),
  authCallback: null as
    ((event: string, session?: { user: { id: string }; access_token: string }) => void) | null,
  pathname: "/en/reset-password",
}));
vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: mocks.client,
}));
vi.mock("next-intl/server", () => ({
  getRequestConfig: (config: unknown) => config,
  setRequestLocale: vi.fn(),
  getMessages: vi.fn(async () => ({ common })),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push, refresh: mocks.refresh }),
  usePathname: () => mocks.pathname,
}));
async function renderRoute(confirm = false, locale = "en") {
  const params = Promise.resolve({ locale });
  const page = await (confirm ? ConfirmPage({ params }) : RequestPage({ params }));
  return render(await RecoveryLayout({ params, children: page }));
}

beforeEach(() => {
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  vi.resetAllMocks();
  mocks.authCallback = null;
  mocks.pathname = "/en/reset-password";
  window.history.replaceState({}, "", "/en/reset-password?next=https://evil.example.test");
  mocks.client.mockResolvedValue({
    auth: {
      resetPasswordForEmail: mocks.reset,
      exchangeCodeForSession: mocks.exchange,
      updateUser: mocks.update,
      getSession: mocks.session,
      getClaims: mocks.claims,
      onAuthStateChange: (
        callback: (event: string, session?: { user: { id: string }; access_token: string }) => void,
      ) => {
        mocks.authCallback = callback;
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      },
    },
  });
  mocks.reset.mockResolvedValue({ error: null });
  mocks.exchange.mockImplementation(async () => {
    mocks.authCallback?.("PASSWORD_RECOVERY", {
      user: { id: "recovery-user" },
      access_token: "recovery-token",
    });
    return {
      data: { session: { user: { id: "recovery-user" }, access_token: "recovery-token" } },
      error: null,
    };
  });
  mocks.update.mockResolvedValue({ error: null });
  mocks.session.mockResolvedValue({
    data: { session: { user: { id: "recovery-user" }, access_token: "recovery-token" } },
  });
  mocks.claims.mockResolvedValue({
    data: { claims: { sub: "recovery-user", session_id: "recovery-session" } },
    error: null,
  });
  mocks.fetch.mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", mocks.fetch);
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://staging.example.supabase.co/");
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "public-fixture-key");
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("shared vendor password recovery forms with isolated Auth fixtures", () => {
  it("renders the request form without loading Auth or sending an email", async () => {
    await renderRoute();
    expect(screen.getByRole("heading", { name: "Reset your password" })).toBeInTheDocument();
    expect(mocks.client).not.toHaveBeenCalled();
  });

  it("keeps the recovery form outside operational vendor navigation", async () => {
    render(
      <NextIntlClientProvider locale="en" messages={{ vendor, auth, common }}>
        <VendorShell locale="en" capabilities={capabilities}>
          <ResetRequestForm locale="en" />
        </VendorShell>
      </NextIntlClientProvider>,
    );
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send reset link" })).toBeInTheDocument();
  });

  it("can move from recovery to the vendor shell without changing hook order", async () => {
    const wrap = () => (
      <NextIntlClientProvider locale="en" messages={{ vendor, common }}>
        <ThemeProvider>
          <VendorShell locale="en" capabilities={capabilities}>
            <p>Fixture</p>
          </VendorShell>
        </ThemeProvider>
      </NextIntlClientProvider>
    );
    const view = render(wrap());
    mocks.pathname = "/en/orders";
    view.rerender(wrap());
    expect(screen.getAllByRole("navigation")[0]).toBeInTheDocument();
    mocks.pathname = "/en/reset-password/confirm";
    view.rerender(wrap());
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("requires email, then requests a same-origin confirmation and shows neutral confirmation", async () => {
    const user = userEvent.setup();
    await renderRoute();
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(mocks.client).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/email address/i), "fixture@example.test");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(mocks.reset).toHaveBeenCalledExactlyOnceWith("fixture@example.test", {
      redirectTo: `${window.location.origin}/en/reset-password/confirm`,
    });
    expect(await screen.findByRole("status")).toHaveTextContent("If an account exists");
    expect(screen.getByRole("link", { name: "Back to sign in" })).toHaveAttribute(
      "href",
      "/en/login",
    );
  });

  it.each(["returned", "rejected", "throttled"])(
    "shows a retryable request failure: %s",
    async (kind) => {
      if (kind === "rejected") mocks.reset.mockRejectedValue(new Error("fixture"));
      else
        mocks.reset.mockResolvedValue({
          error:
            kind === "throttled"
              ? { status: 429, message: "after 30 seconds" }
              : { message: "fixture" },
        });
      await renderRoute();
      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: "fixture@example.test" },
      });
      fireEvent.submit(screen.getByRole("button", { name: "Send reset link" }).closest("form")!);
      expect(await screen.findByRole("alert")).toBeInTheDocument();
      await waitFor(() =>
        expect(screen.getByRole("button", { name: "Send reset link" })).toBeEnabled(),
      );
    },
  );

  it("disables repeat requests while waiting for Auth", async () => {
    let finish!: (value: { error: null }) => void;
    mocks.reset.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    const user = userEvent.setup();
    await renderRoute();
    await user.type(screen.getByLabelText(/email address/i), "fixture@example.test");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(screen.getByRole("button", { name: /sending/i })).toBeDisabled();
    expect(mocks.reset).toHaveBeenCalledOnce();
    finish({ error: null });
    await screen.findByRole("status");
  });

  it.each(["missing", "expired"])(
    "shows the recovery link failure and correct retry route: %s",
    async (kind) => {
      if (kind === "expired") {
        window.history.replaceState({}, "", "/en/reset-password/confirm?code=fixture");
        mocks.exchange.mockResolvedValue({ error: { message: "expired" } });
      }
      await renderRoute(true);
      expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
      expect(screen.getByRole("link", { name: "Send reset link" })).toHaveAttribute(
        "href",
        "/en/reset-password",
      );
      expect(mocks.update).not.toHaveBeenCalled();
    },
  );

  it("validates passwords, displays save errors, then returns only to vendor login on success", async () => {
    window.history.replaceState(
      {},
      "",
      "/en/reset-password/confirm?code=fixture&next=https://evil.example.test",
    );
    await renderRoute(true);
    const password = await screen.findByLabelText(/^new password/i);
    const confirm = screen.getByLabelText(/^confirm new password/i);
    const submit = () =>
      fireEvent.submit(screen.getByRole("button", { name: "Update password" }).closest("form")!);
    fireEvent.change(password, { target: { value: "short" } });
    submit();
    expect(screen.getByRole("alert")).toHaveTextContent("at least 8");
    fireEvent.change(password, { target: { value: "fixture-password" } });
    submit();
    expect(screen.getByRole("alert")).toHaveTextContent("do not match");
    expect(mocks.update).not.toHaveBeenCalled();
    fireEvent.change(confirm, { target: { value: "fixture-password" } });
    mocks.fetch.mockResolvedValueOnce({ ok: false, status: 500, headers: { get: () => null } });
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Update password" })).toBeEnabled(),
    );
    submit();
    expect(await screen.findByRole("status")).toHaveTextContent("Password updated");
    fireEvent.click(screen.getByRole("button", { name: "Go to sign in" }));
    expect(mocks.exchange).toHaveBeenCalledExactlyOnceWith("fixture");
    expect(mocks.fetch).toHaveBeenCalledTimes(2);
    expect(mocks.fetch).toHaveBeenLastCalledWith(
      "https://staging.example.supabase.co/auth/v1/user",
      expect.objectContaining({
        method: "PUT",
        headers: expect.objectContaining({ Authorization: "Bearer recovery-token" }),
        body: JSON.stringify({ password: "fixture-password" }),
      }),
    );
    expect(mocks.push).toHaveBeenCalledExactlyOnceWith("/en/login");
    expect(mocks.refresh).toHaveBeenCalledOnce();
  });

  it("lets Auth reject reused codes and never logs recovery codes or passwords", async () => {
    const log = vi.spyOn(console, "log");
    const error = vi.spyOn(console, "error");
    const warn = vi.spyOn(console, "warn");
    try {
      window.history.replaceState({}, "", "/en/reset-password/confirm?code=fixture-reused-code");
      mocks.exchange.mockResolvedValue({ error: { message: "fixture-reused-code" } });
      await renderRoute(true);
      expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
      cleanup();
      await renderRoute(true);
      expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
      expect(mocks.exchange).toHaveBeenCalledTimes(2);
      expect(mocks.update).not.toHaveBeenCalled();
      expect(log).not.toHaveBeenCalled();
      expect(error).not.toHaveBeenCalled();
      expect(warn).not.toHaveBeenCalled();
    } finally {
      log.mockRestore();
      error.mockRestore();
      warn.mockRestore();
    }
  });
});

describe("vendor recovery route wiring", () => {
  it("provides both recovery pages for every supported locale", () => {
    expect(requestParams()).toEqual(LOCALES.map((locale) => ({ locale })));
    expect(confirmParams()).toEqual(requestParams());
  });
  it("does not render unsupported locales", async () => {
    const params = Promise.resolve({ locale: "xx" });
    expect(await RequestPage({ params })).toBeNull();
    expect(await ConfirmPage({ params })).toBeNull();
    expect(await RecoveryLayout({ params, children: <p>Fixture</p> })).toBeNull();
  });
  it.each(LOCALES)(
    "uses the %s locale for the same-origin callback and return link",
    async (locale) => {
      const view = await renderRoute(false, locale);
      const input = screen.getByRole("textbox");
      expect(input).toHaveAttribute("type", "email");
      expect(input).toHaveAccessibleName();
      fireEvent.change(input, { target: { value: "fixture@example.test" } });
      fireEvent.submit(view.container.querySelector("form")!);
      await screen.findByRole("status");
      expect(mocks.reset).toHaveBeenCalledExactlyOnceWith("fixture@example.test", {
        redirectTo: `${window.location.origin}/${locale}/reset-password/confirm`,
      });
      expect(screen.getByRole("link")).toHaveAttribute("href", `/${locale}/login`);
    },
  );
  it("supports keyboard entry and submission with labeled controls", async () => {
    const user = userEvent.setup();
    await renderRoute();
    await user.tab();
    expect(screen.getByLabelText(/email address/i)).toHaveFocus();
    await user.keyboard("fixture@example.test");
    await user.tab();
    expect(screen.getByRole("button", { name: "Send reset link" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("status")).toHaveTextContent("If an account exists");
    expect(mocks.reset).toHaveBeenCalledOnce();
  });
  it("does not exchange a code after leaving recovery during a lazy Auth load", async () => {
    let resolve!: (value: unknown) => void;
    mocks.client.mockReturnValue(
      new Promise((done) => {
        resolve = done;
      }),
    );
    window.history.replaceState({}, "", "/en/reset-password/confirm?code=synthetic-fixture");
    const view = await renderRoute(true);
    view.unmount();
    await act(async () =>
      resolve({ auth: { exchangeCodeForSession: mocks.exchange, getSession: mocks.session } }),
    );
    expect(mocks.exchange).not.toHaveBeenCalled();
    expect(mocks.update).not.toHaveBeenCalled();
  });
  it("ignores a delayed exchange after leaving recovery and preserves a fresh route", async () => {
    let resolve!: (value: { error: null }) => void;
    mocks.exchange.mockReturnValueOnce(
      new Promise((done) => {
        resolve = done;
      }),
    );
    window.history.replaceState({}, "", "/en/reset-password/confirm?code=synthetic-fixture");
    const old = await renderRoute(true);
    await waitFor(() => expect(mocks.exchange).toHaveBeenCalledOnce());
    old.unmount();
    window.history.replaceState({}, "", "/en/reset-password/confirm");
    await renderRoute(true);
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
    await act(async () => resolve({ error: null }));
    expect(screen.getByRole("alert")).toHaveTextContent("invalid or has expired");
    expect(screen.queryByRole("button", { name: "Update password" })).not.toBeInTheDocument();
    expect(mocks.update).not.toHaveBeenCalled();
  });
});
