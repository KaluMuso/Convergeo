// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const signInWithPassword = vi.fn();
const getSession = vi.fn();
const getPreferences = vi.fn();
const push = vi.fn();
const refresh = vi.fn();

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: { signInWithPassword, getSession },
  }),
}));

vi.mock("../../account/_components/account-api", () => ({
  createAccountApiClient: () => ({
    getPreferences,
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

import { EmailForm } from "./email-form";

const labels = {
  emailLabel: "Email address",
  passwordLabel: "Password",
  submit: "Sign in with email",
  loading: "Please wait",
  required: "Required",
  invalidEmail: "Invalid email",
  invalidPassword: "Invalid password",
  generic: "Generic error",
  throttled: "Try again in {seconds} seconds",
  invalidCredentials: "Incorrect email or password.",
  emailNotConfirmed: "Confirm email",
  alreadyRegistered: "Already registered",
};

describe("EmailForm portal post-auth", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  beforeEach(() => {
    signInWithPassword.mockResolvedValue({ error: null });
    getSession.mockResolvedValue({ data: { session: { access_token: "tok" } } });
    getPreferences.mockResolvedValue({ onboarding: { completed_at: "2026-01-01T00:00:00Z" } });
  });

  async function submit(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByLabelText(/email address/i), "owner@example.com");
    await user.type(screen.getByLabelText(/password/i), "password1");
    await user.click(screen.getByRole("button", { name: "Sign in with email" }));
  }

  it("customer login still fetches preferences after successful auth", async () => {
    const user = userEvent.setup();
    render(
      <EmailForm
        locale="en"
        labels={labels}
        mode="login"
        portal="customer"
        defaultNextPath="/en"
      />,
    );

    await submit(user);

    await waitFor(() => {
      expect(signInWithPassword).toHaveBeenCalled();
      expect(getPreferences).toHaveBeenCalled();
      expect(push).toHaveBeenCalledWith("/en");
    });
  });

  it("vendor login authenticates without calling customer preferences", async () => {
    const user = userEvent.setup();
    render(
      <EmailForm
        locale="en"
        labels={labels}
        mode="login"
        portal="vendor"
        defaultNextPath="/en"
        nextParam="/en/listings"
      />,
    );

    await submit(user);

    await waitFor(() => {
      expect(signInWithPassword).toHaveBeenCalled();
      expect(getPreferences).not.toHaveBeenCalled();
      expect(push).toHaveBeenCalledWith("/en/listings");
    });
  });

  it("admin login authenticates without calling customer preferences", async () => {
    const user = userEvent.setup();
    render(
      <EmailForm locale="en" labels={labels} mode="login" portal="admin" defaultNextPath="/en" />,
    );

    await submit(user);

    await waitFor(() => {
      expect(signInWithPassword).toHaveBeenCalled();
      expect(getPreferences).not.toHaveBeenCalled();
      expect(push).toHaveBeenCalledWith("/en");
    });
  });
});
