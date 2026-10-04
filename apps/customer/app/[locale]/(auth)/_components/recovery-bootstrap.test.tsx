// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import auth from "../../../../../../packages/i18n/messages/en/auth.json";

import { ResetConfirmForm } from "./reset-confirm-form";

const mocks = vi.hoisted(() => ({
  client: vi.fn(),
  exchange: vi.fn(),
  session: vi.fn(),
  update: vi.fn(),
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
  window.history.replaceState({}, "", "/en/reset-password/confirm");
  mocks.client.mockResolvedValue({
    auth: {
      exchangeCodeForSession: mocks.exchange,
      getSession: mocks.session,
      updateUser: mocks.update,
    },
  });
  mocks.exchange.mockResolvedValue({ error: null });
  mocks.session.mockResolvedValue({ data: { session: null } });
});
afterEach(() => cleanup());

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
  it.each(["client", "exchange", "session"])(
    "exits checking safely when %s rejects",
    async (kind) => {
      if (kind === "exchange")
        window.history.replaceState({}, "", "/en/reset-password/confirm?code=synthetic-fixture");
      mocks[kind as "client" | "exchange" | "session"].mockRejectedValue(
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
      expect(mocks.update).not.toHaveBeenCalled();
    },
  );

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

  it.each(["exchange", "session"])(
    "ignores a delayed %s result after unmount and preserves a fresh mount",
    async (kind) => {
      const pending = deferred<unknown>();
      mocks[kind as "exchange" | "session"].mockReturnValueOnce(pending.promise);
      if (kind === "exchange")
        window.history.replaceState({}, "", "/en/reset-password/confirm?code=synthetic-fixture");
      const old = renderRecovery();
      await waitFor(() => expect(mocks[kind as "exchange" | "session"]).toHaveBeenCalledOnce());
      old.unmount();
      window.history.replaceState({}, "", "/en/reset-password/confirm");
      renderRecovery();
      expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
      await act(async () =>
        pending.resolve(kind === "exchange" ? { error: null } : { data: { session: {} } }),
      );
      expect(screen.getByRole("alert")).toHaveTextContent("invalid or has expired");
      expect(screen.queryByRole("button", { name: "Update password" })).not.toBeInTheDocument();
    },
  );

  it.each(["client", "exchange", "session"])(
    "handles delayed %s rejection after unmount",
    async (kind) => {
      const pending = deferred<unknown>();
      mocks[kind as "client" | "exchange" | "session"].mockReturnValueOnce(pending.promise);
      if (kind === "exchange")
        window.history.replaceState({}, "", "/en/reset-password/confirm?code=synthetic-fixture");
      const view = renderRecovery();
      await waitFor(() =>
        expect(mocks[kind as "client" | "exchange" | "session"]).toHaveBeenCalledOnce(),
      );
      view.unmount();
      await act(async () => pending.reject(new Error("synthetic-late-failure")));
      expect(mocks.update).not.toHaveBeenCalled();
    },
  );
});
