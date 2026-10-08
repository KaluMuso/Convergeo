// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import auth from "../../../../../../packages/i18n/messages/en/auth.json";

import { ResetConfirmForm } from "./reset-confirm-form";

const mocks = vi.hoisted(() => ({
  client: vi.fn(),
  exchange: vi.fn(),
  session: vi.fn(),
  claims: vi.fn(),
  fetch: vi.fn(),
  unsubscribe: vi.fn(),
  authCallback: null as
    ((event: string, session?: { user: { id: string }; access_token: string }) => void) | null,
}));
vi.mock("@vergeo/auth/browser-client-lazy", () => ({ getBrowserClient: mocks.client }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

function renderRecovery() {
  return render(
    <NextIntlClientProvider locale="en" messages={{ auth }}>
      <ResetConfirmForm locale="en" />
    </NextIntlClientProvider>,
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.resetAllMocks();
  mocks.authCallback = null;
  window.history.replaceState({}, "", "/en/reset-password/confirm");
  mocks.client.mockResolvedValue({
    auth: {
      exchangeCodeForSession: mocks.exchange,
      getSession: mocks.session,
      getClaims: mocks.claims,
      onAuthStateChange: (
        callback: (event: string, session?: { user: { id: string }; access_token: string }) => void,
      ) => {
        mocks.authCallback = callback;
        return { data: { subscription: { unsubscribe: mocks.unsubscribe } } };
      },
    },
  });
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
  mocks.session.mockResolvedValue({
    data: { session: { user: { id: "recovery-user" }, access_token: "recovery-token" } },
  });
  mocks.claims.mockImplementation(async (token: string) => ({
    data: {
      claims: {
        sub: token === "other-token" ? "other-user" : "recovery-user",
        session_id: token === "other-session-token" ? "other-session" : "recovery-session",
      },
    },
    error: null,
  }));
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

describe("recovery session bootstrap failures and cleanup", () => {
  it("exchanges only once when Strict Mode cancels and restarts bootstrap", async () => {
    window.history.replaceState({}, "", "/en/reset-password/confirm?code=synthetic-fixture");
    render(
      <StrictMode>
        <NextIntlClientProvider locale="en" messages={{ auth }}>
          <ResetConfirmForm locale="en" />
        </NextIntlClientProvider>
      </StrictMode>,
    );
    expect(await screen.findByRole("button", { name: "Update password" })).toBeInTheDocument();
    expect(mocks.exchange).toHaveBeenCalledExactlyOnceWith("synthetic-fixture");
  });
  it.each(["client", "exchange"])("exits checking safely when %s rejects", async (kind) => {
    window.history.replaceState({}, "", "/en/reset-password/confirm?code=synthetic-fixture");
    mocks[kind as "client" | "exchange"].mockRejectedValue(
      new Error("synthetic-bootstrap-failure"),
    );
    renderRecovery();
    expect(await screen.findByRole("alert", {}, { timeout: 300 })).toHaveTextContent(
      "invalid or has expired",
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Send reset link" })).toHaveAttribute(
      "href",
      "/en/reset-password",
    );
    expect(screen.queryByRole("button", { name: "Update password" })).not.toBeInTheDocument();
    expect(mocks.fetch).not.toHaveBeenCalled();
  });

  it("does not start a session exchange after an unmounted lazy load resolves", async () => {
    const pending = deferred<unknown>();
    mocks.client.mockReturnValue(pending.promise);
    window.history.replaceState({}, "", "/en/reset-password/confirm?code=synthetic-fixture");
    const view = renderRecovery();
    view.unmount();
    await act(async () =>
      pending.resolve({
        auth: { exchangeCodeForSession: mocks.exchange, getSession: mocks.session },
      }),
    );
    expect(mocks.exchange).not.toHaveBeenCalled();
    expect(mocks.session).not.toHaveBeenCalled();
  });

  it("ignores a delayed exchange result after unmount and preserves a fresh mount", async () => {
    const pending = deferred<unknown>();
    mocks.exchange.mockReturnValueOnce(pending.promise);
    window.history.replaceState({}, "", "/en/reset-password/confirm?code=synthetic-fixture");
    const old = renderRecovery();
    await waitFor(() => expect(mocks.exchange).toHaveBeenCalledOnce());
    old.unmount();
    window.history.replaceState({}, "", "/en/reset-password/confirm");
    renderRecovery();
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
    await act(async () => pending.resolve({ error: null }));
    expect(screen.getByRole("alert")).toHaveTextContent("invalid or has expired");
    expect(screen.queryByRole("button", { name: "Update password" })).not.toBeInTheDocument();
  });

  it.each(["client", "exchange"])("handles delayed %s rejection after unmount", async (kind) => {
    const pending = deferred<unknown>();
    mocks[kind as "client" | "exchange"].mockReturnValueOnce(pending.promise);
    window.history.replaceState({}, "", "/en/reset-password/confirm?code=synthetic-fixture");
    const view = renderRecovery();
    await waitFor(() => expect(mocks[kind as "client" | "exchange"]).toHaveBeenCalledOnce());
    view.unmount();
    await act(async () => pending.reject(new Error("synthetic-late-failure")));
    expect(mocks.fetch).not.toHaveBeenCalled();
  });

  it("rejects a code-less visit even with another account already signed in", async () => {
    mocks.session.mockResolvedValue({ data: { session: { user: { id: "other-account" } } } });
    renderRecovery();
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
    expect(mocks.session).not.toHaveBeenCalled();
    expect(mocks.fetch).not.toHaveBeenCalled();
  });

  it("rejects a valid sign-in code that lacks the recovery event", async () => {
    window.history.replaceState({}, "", "/en/reset-password/confirm?code=oauth-fixture");
    mocks.exchange.mockImplementation(async () => {
      mocks.authCallback?.("SIGNED_IN", {
        user: { id: "other-user" },
        access_token: "other-token",
      });
      return {
        data: { session: { user: { id: "other-user" }, access_token: "other-token" } },
        error: null,
      };
    });
    renderRecovery();
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
    expect(mocks.fetch).not.toHaveBeenCalled();
    expect(mocks.unsubscribe).toHaveBeenCalledOnce();
  });

  it.each([
    ["other-user", "other-token"],
    ["recovery-user", "signin-token"],
  ])(
    "rejects an unrelated recovery event before a sign-in exchange for %s",
    async (userId, accessToken) => {
      window.history.replaceState({}, "", "/en/reset-password/confirm?code=oauth-fixture");
      mocks.exchange.mockImplementation(async () => {
        mocks.authCallback?.("PASSWORD_RECOVERY", {
          user: { id: "recovery-user" },
          access_token: "recovery-token",
        });
        mocks.authCallback?.("SIGNED_IN", {
          user: { id: userId },
          access_token: accessToken,
        });
        return {
          data: { session: { user: { id: userId }, access_token: accessToken } },
          error: null,
        };
      });
      renderRecovery();
      expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
      expect(mocks.fetch).not.toHaveBeenCalled();
    },
  );

  it("does not update another account after a recovery session switches", async () => {
    window.history.replaceState({}, "", "/en/reset-password/confirm?code=recovery-fixture");
    renderRecovery();
    expect(await screen.findByRole("button", { name: "Update password" })).toBeInTheDocument();
    mocks.session.mockResolvedValue({
      data: { session: { user: { id: "other-user" }, access_token: "other-token" } },
    });
    const password = screen.getByLabelText(/^New password/i);
    const confirmation = screen.getByLabelText(/^Confirm new password/i);
    fireEvent.change(password, { target: { value: "fixture-password" } });
    fireEvent.change(confirmation, { target: { value: "fixture-password" } });
    fireEvent.submit(screen.getByRole("button", { name: "Update password" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
    expect(mocks.fetch).not.toHaveBeenCalled();
  });

  it("accepts a refreshed token from the same recovery session", async () => {
    window.history.replaceState({}, "", "/en/reset-password/confirm?code=recovery-fixture");
    renderRecovery();
    await screen.findByRole("button", { name: "Update password" });
    mocks.session.mockResolvedValue({
      data: { session: { user: { id: "recovery-user" }, access_token: "refreshed-token" } },
    });
    fireEvent.change(screen.getByLabelText(/^New password/i), {
      target: { value: "fixture-password" },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm new password/i), {
      target: { value: "fixture-password" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Update password" }).closest("form")!);
    expect(await screen.findByRole("status")).toHaveTextContent("Password updated");
    expect(mocks.fetch).toHaveBeenCalledExactlyOnceWith(
      "https://staging.example.supabase.co/auth/v1/user",
      expect.objectContaining({
        method: "PUT",
        headers: expect.objectContaining({ Authorization: "Bearer refreshed-token" }),
        body: JSON.stringify({ password: "fixture-password" }),
      }),
    );
  });

  it("rejects another session for the same user", async () => {
    window.history.replaceState({}, "", "/en/reset-password/confirm?code=recovery-fixture");
    renderRecovery();
    await screen.findByRole("button", { name: "Update password" });
    mocks.session.mockResolvedValue({
      data: {
        session: { user: { id: "recovery-user" }, access_token: "other-session-token" },
      },
    });
    fireEvent.change(screen.getByLabelText(/^New password/i), {
      target: { value: "fixture-password" },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm new password/i), {
      target: { value: "fixture-password" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Update password" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
    expect(mocks.fetch).not.toHaveBeenCalled();
  });

  it("pins the password request if another tab switches accounts during submission", async () => {
    window.history.replaceState({}, "", "/en/reset-password/confirm?code=recovery-fixture");
    renderRecovery();
    await screen.findByRole("button", { name: "Update password" });
    mocks.fetch.mockImplementation(async () => {
      mocks.session.mockResolvedValue({
        data: { session: { user: { id: "other-user" }, access_token: "other-token" } },
      });
      return { ok: true };
    });
    fireEvent.change(screen.getByLabelText(/^New password/i), {
      target: { value: "fixture-password" },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm new password/i), {
      target: { value: "fixture-password" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Update password" }).closest("form")!);
    expect(await screen.findByRole("status")).toHaveTextContent("Password updated");
    expect(mocks.fetch).toHaveBeenCalledExactlyOnceWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer recovery-token" }),
      }),
    );
    expect(mocks.session).toHaveBeenCalledTimes(1);
  });
});
