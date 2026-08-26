// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: {
      signInWithOtp: vi.fn(),
      verifyOtp: vi.fn(),
      exchangeCodeForSession: vi.fn(),
      getSession: vi.fn(),
      signInWithPassword: vi.fn(),
      signUp: vi.fn(),
    },
  }),
}));

vi.mock("../../account/_components/account-api", () => ({
  createAccountApiClient: () => ({ getPreferences: vi.fn() }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

import { AuthLoginShell, type AuthLoginLabels } from "./login-shell";

const labels: AuthLoginLabels = {
  title: "Sign in",
  subtitle: "Welcome back",
  phone: {
    countryCode: "Country code",
    nationalNumber: "Phone number",
    phoneLabel: "Mobile number",
    phoneHelp: "SMS help",
    phonePlaceholder: "97 123 4567",
    submit: "Continue with phone",
    loading: "Loading",
    required: "Required",
    invalidPhone: "Invalid phone",
    sendFailed: "Send failed",
    throttled: "Try again in {seconds} seconds",
  },
  email: {
    emailLabel: "Email address",
    passwordLabel: "Password",
    submit: "Sign in with email",
    loading: "Loading",
    required: "Required",
    invalidEmail: "Invalid email",
    invalidPassword: "Invalid password",
    generic: "Generic error",
    throttled: "Try again in {seconds} seconds",
    invalidCredentials: "Invalid credentials",
    emailNotConfirmed: "Email not confirmed",
    alreadyRegistered: "Already registered",
    forgotPassword: "Forgot password?",
  },
  divider: "or",
  emailToggle: "Use email instead",
  phoneToggle: "Use phone instead",
  google: "Continue with Google",
  googleLoading: "Signing in with Google",
  genericError: "Something went wrong",
};

/**
 * D25/PR-D: the shared shell is the ONE decision point for whether phone OTP
 * is offered per portal (`apps/vendor` and `apps/admin` both render this
 * exact component through cross-app imports — see their login `page.tsx`).
 * These cases pin each portal's contract so a future default/prop change in
 * this file cannot silently re-disable — or accidentally enable — phone
 * login on a portal without a test failing here first.
 */
describe("AuthLoginShell — per-portal phone/email contract", () => {
  it("vendor: phone form renders by default and email/password stays reachable via toggle", async () => {
    const user = userEvent.setup();
    render(
      <AuthLoginShell
        locale="en"
        variant="vendor"
        labels={labels}
        defaultNextPath="/en"
        showSignupLink={false}
      />,
    );

    // Default method is phone — this is the regression the vendor login page
    // previously failed: phoneEnabled={false} rendered EmailForm only.
    expect(screen.getByRole("textbox", { name: /phone|mobile/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/email address/i)).not.toBeInTheDocument();

    // The toggle is present and switches to email/password without losing it.
    const toggle = screen.getByRole("button", { name: "Use email instead" });
    await user.click(toggle);

    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /phone|mobile/i })).not.toBeInTheDocument();

    // And back to phone — the email/password path never disappears from the UI.
    await user.click(screen.getByRole("button", { name: "Use phone instead" }));
    expect(screen.getByRole("textbox", { name: /phone|mobile/i })).toBeInTheDocument();
  });

  it("admin: phone authentication remains disabled — email/password only, no toggle", () => {
    render(
      <AuthLoginShell
        locale="en"
        variant="admin"
        labels={labels}
        defaultNextPath="/en"
        showSignupLink={false}
        phoneEnabled={false}
      />,
    );

    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /phone|mobile/i })).not.toBeInTheDocument();
    // No method toggle at all when phone is disabled — nothing to switch between.
    expect(
      screen.queryByRole("button", { name: /use (email|phone) instead/i }),
    ).not.toBeInTheDocument();
  });

  it("customer: existing default behavior unchanged — phone first, toggle to email", () => {
    render(<AuthLoginShell locale="en" variant="customer" labels={labels} defaultNextPath="/en" />);

    expect(screen.getByRole("textbox", { name: /phone|mobile/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use email instead" })).toBeInTheDocument();
  });
});
