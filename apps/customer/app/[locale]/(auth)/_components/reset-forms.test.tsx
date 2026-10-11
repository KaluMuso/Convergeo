// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const resetPasswordForEmail = vi.fn();
const exchangeCodeForSession = vi.fn();
const updateUser = vi.fn();
const getSession = vi.fn();

vi.mock("@vergeo/auth/browser-client", () => ({
  createBrowserClient: () => ({
    auth: { resetPasswordForEmail, exchangeCodeForSession, updateUser, getSession },
  }),
}));

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

import { ResetConfirmForm } from "./reset-confirm-form";
import { ResetRequestForm } from "./reset-request-form";

const messages = {
  auth: {
    errors: { required: "Required", generic: "Something went wrong", throttled: "Wait {seconds}s" },
    reset: {
      requestTitle: "Reset your password",
      requestSubtitle: "Enter your email",
      emailLabel: "Email address",
      requestSubmit: "Send reset link",
      requestSending: "Sending",
      requestSent: "If an account exists for {email}, a reset link is on its way.",
      backToLogin: "Back to sign in",
      confirmTitle: "Set a new password",
      confirmSubtitle: "Choose a new password",
      newPasswordLabel: "New password",
      confirmPasswordLabel: "Confirm new password",
      confirmSubmit: "Update password",
      confirmSaving: "Updating",
      confirmSuccess: "Password updated. You can now sign in.",
      goToLogin: "Go to sign in",
      checking: "Checking your reset link",
      linkInvalid: "This reset link is invalid or has expired.",
      mismatch: "Passwords do not match.",
      invalidPassword: "Password must be at least 8 characters.",
    },
  },
};

function renderWithIntl(node: React.ReactNode) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      {node}
    </NextIntlClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.history.replaceState({}, "", "/");
});

beforeEach(() => {
  resetPasswordForEmail.mockResolvedValue({ error: null });
  exchangeCodeForSession.mockResolvedValue({ error: null });
  updateUser.mockResolvedValue({ error: null });
  getSession.mockResolvedValue({ data: { session: null } });
});

describe("ResetRequestForm", () => {
  it("emails a reset link and shows the neutral confirmation", async () => {
    const user = userEvent.setup();
    renderWithIntl(<ResetRequestForm locale="en" />);

    await user.type(screen.getByLabelText(/email address/i), "founder@example.com");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => expect(resetPasswordForEmail).toHaveBeenCalledTimes(1));
    const [emailArg, opts] = resetPasswordForEmail.mock.calls[0] as [
      string,
      { redirectTo: string },
    ];
    expect(emailArg).toBe("founder@example.com");
    expect(opts.redirectTo).toBe(`${window.location.origin}/en/reset-password/confirm`);
    expect(screen.getByText(/a reset link is on its way/i)).toBeInTheDocument();
  });

  it("requires an email before submitting", async () => {
    const user = userEvent.setup();
    renderWithIntl(<ResetRequestForm locale="en" />);
    await user.click(screen.getByRole("button", { name: /send reset link/i }));
    expect(resetPasswordForEmail).not.toHaveBeenCalled();
    expect(screen.getByText("Required")).toBeInTheDocument();
  });
});

describe("ResetConfirmForm", () => {
  it("exchanges the recovery code, rejects mismatched passwords, then updates", async () => {
    window.history.replaceState({}, "", "/en/reset-password/confirm?code=abc123");
    const user = userEvent.setup();
    renderWithIntl(<ResetConfirmForm locale="en" />);

    await waitFor(() => expect(exchangeCodeForSession).toHaveBeenCalledWith("abc123"));
    const inputs = screen.getAllByLabelText(/password/i);
    const newPw = inputs[0] as HTMLElement;
    const confirmPw = inputs[1] as HTMLElement;

    // Mismatch is rejected client-side.
    await user.type(newPw, "supersecret1");
    await user.type(confirmPw, "different1");
    await user.click(screen.getByRole("button", { name: /update password/i }));
    expect(updateUser).not.toHaveBeenCalled();
    expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();

    // Matching passwords update and show success.
    await user.clear(confirmPw);
    await user.type(confirmPw, "supersecret1");
    await user.click(screen.getByRole("button", { name: /update password/i }));
    await waitFor(() => expect(updateUser).toHaveBeenCalledWith({ password: "supersecret1" }));
    expect(screen.getByText(/password updated/i)).toBeInTheDocument();
  });

  it("shows an invalid-link message when there is no code and no session", async () => {
    renderWithIntl(<ResetConfirmForm locale="en" />);
    await waitFor(() =>
      expect(screen.getByText(/reset link is invalid or has expired/i)).toBeInTheDocument(),
    );
    expect(exchangeCodeForSession).not.toHaveBeenCalled();
  });

  it("shows the password form for an established session without a code or URL errors", async () => {
    window.history.replaceState({}, "", "/en/reset-password/confirm");
    getSession.mockResolvedValue({ data: { session: { access_token: "recovery-session" } } });
    renderWithIntl(<ResetConfirmForm locale="en" />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /update password/i })).toBeInTheDocument(),
    );
    expect(screen.getAllByLabelText(/password/i)).toHaveLength(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(getSession).toHaveBeenCalledTimes(1);
    expect(exchangeCodeForSession).not.toHaveBeenCalled();
    expect(updateUser).not.toHaveBeenCalled();
  });

  it("rejects an expired code and never offers the password form", async () => {
    window.history.replaceState({}, "", "/en/reset-password/confirm?code=expired");
    exchangeCodeForSession.mockResolvedValue({ error: { message: "expired" } });
    renderWithIntl(<ResetConfirmForm locale="en" />);
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/invalid or has expired/i),
    );
    expect(updateUser).not.toHaveBeenCalled();
  });

  it.each([
    ["query error", "?error=access_denied"],
    ["query error_code", "?error_code=otp_expired"],
    ["fragment error", "#error=access_denied"],
    ["fragment error_code", "#error_code=otp_expired"],
    ["code with fragment error", "?code=valid#state=x&error=access_denied"],
  ])("rejects %s with and without an unrelated session", async (_name, suffix) => {
    for (const session of [null, { access_token: "other-session" }]) {
      window.history.replaceState({}, "", `/en/reset-password/confirm${suffix}`);
      getSession.mockResolvedValue({ data: { session } });
      const view = renderWithIntl(<ResetConfirmForm locale="en" />);
      await waitFor(() =>
        expect(screen.getByRole("alert")).toHaveTextContent(/invalid or has expired/i),
      );
      expect(screen.queryByRole("button", { name: /update password/i })).not.toBeInTheDocument();
      expect(exchangeCodeForSession).not.toHaveBeenCalled();
      expect(getSession).not.toHaveBeenCalled();
      expect(updateUser).not.toHaveBeenCalled();
      view.unmount();
    }
  });

  it("ends checking when code exchange rejects", async () => {
    window.history.replaceState({}, "", "/en/reset-password/confirm?code=bad");
    exchangeCodeForSession.mockRejectedValue(new Error("network unavailable"));
    renderWithIntl(<ResetConfirmForm locale="en" />);
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/invalid or has expired/i),
    );
  });

  it("exchanges a single-use code once under React strict effects", async () => {
    window.history.replaceState({}, "", "/en/reset-password/confirm?code=single-use");
    renderWithIntl(
      <React.StrictMode>
        <ResetConfirmForm locale="en" />
      </React.StrictMode>,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /update password/i })).toBeInTheDocument(),
    );
    expect(exchangeCodeForSession).toHaveBeenCalledTimes(1);
  });
});
