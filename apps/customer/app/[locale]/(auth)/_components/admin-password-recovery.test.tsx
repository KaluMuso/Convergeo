// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "@vergeo/ui/src/theme-provider";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import admin from "../../../../../../packages/i18n/messages/en/admin.json";
import auth from "../../../../../../packages/i18n/messages/en/auth.json";
import common from "../../../../../../packages/i18n/messages/en/common.json";
import { AdminShell } from "../../../../../admin/app/[locale]/_components/admin-shell";
import { resolveAdminNavCapabilities } from "../../../../../admin/lib/admin-nav-capabilities";

import { ResetConfirmForm } from "./reset-confirm-form";
import { ResetRequestForm } from "./reset-request-form";

const mocks = vi.hoisted(() => ({
  client: vi.fn(),
  reset: vi.fn(),
  exchange: vi.fn(),
  update: vi.fn(),
  session: vi.fn(),
  push: vi.fn(),
  refresh: vi.fn(),
  authCallback: null as
    ((event: string, session?: { user: { id: string }; access_token: string }) => void) | null,
  pathname: "/en/reset-password",
}));
vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: mocks.client,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push, refresh: mocks.refresh }),
  usePathname: () => mocks.pathname,
}));
async function renderRoute(confirm = false) {
  return render(
    <NextIntlClientProvider locale="en" messages={{ auth, common }}>
      {confirm ? <ResetConfirmForm locale="en" /> : <ResetRequestForm locale="en" />}
    </NextIntlClientProvider>,
  );
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
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("shared admin password recovery forms with isolated Auth fixtures", () => {
  it("renders the request form without loading Auth or sending an email", async () => {
    await renderRoute();
    expect(screen.getByRole("heading", { name: "Reset your password" })).toBeInTheDocument();
    expect(mocks.client).not.toHaveBeenCalled();
  });

  it("keeps the recovery form outside operational admin navigation", async () => {
    render(
      <NextIntlClientProvider locale="en" messages={{ admin, auth, common }}>
        <AdminShell locale="en" capabilities={resolveAdminNavCapabilities()}>
          <ResetRequestForm locale="en" />
        </AdminShell>
      </NextIntlClientProvider>,
    );
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send reset link" })).toBeInTheDocument();
  });

  it("can move from recovery to the admin shell without changing hook order", async () => {
    const wrap = () => (
      <NextIntlClientProvider locale="en" messages={{ admin, common }}>
        <ThemeProvider>
          <AdminShell locale="en" capabilities={resolveAdminNavCapabilities()}>
            <p>Fixture</p>
          </AdminShell>
        </ThemeProvider>
      </NextIntlClientProvider>
    );
    const view = render(wrap());
    mocks.pathname = "/en/orders";
    view.rerender(wrap());
    expect(screen.getByRole("navigation")).toBeInTheDocument();
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

  it("validates passwords, displays save errors, then returns only to admin login on success", async () => {
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
    mocks.update.mockResolvedValueOnce({ error: { message: "fixture" } });
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Update password" })).toBeEnabled(),
    );
    submit();
    expect(await screen.findByRole("status")).toHaveTextContent("Password updated");
    fireEvent.click(screen.getByRole("button", { name: "Go to sign in" }));
    expect(mocks.exchange).toHaveBeenCalledExactlyOnceWith("fixture");
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
