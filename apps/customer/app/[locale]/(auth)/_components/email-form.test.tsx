// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const signInWithPassword = vi.fn();
const signUp = vi.fn();
const getSession = vi.fn();
const getPreferences = vi.fn();
const { getReadyCustomerSession } = vi.hoisted(() => ({
  getReadyCustomerSession: vi.fn(),
}));
const push = vi.fn();
const refresh = vi.fn();

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: { signInWithPassword, signUp, getSession },
  }),
}));

vi.mock("../../account/_components/account-api", () => ({
  createAccountApiClient: () => ({
    getPreferences,
  }),
}));

vi.mock("../../../../lib/customer-session", () => ({
  getReadyCustomerSession,
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
  signupConfirmation: "If an account can be created, check your email before signing in.",
};

describe("EmailForm portal post-auth", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  beforeEach(() => {
    signInWithPassword.mockResolvedValue({ error: null });
    signUp.mockResolvedValue({
      data: { user: { id: "new-user" }, session: { access_token: "tok" } },
      error: null,
    });
    getSession.mockResolvedValue({ data: { session: { access_token: "tok" } } });
    getPreferences.mockResolvedValue({ onboarding: { completed_at: "2026-01-01T00:00:00Z" } });
    getReadyCustomerSession.mockResolvedValue({ access_token: "tok" });
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
      expect(getReadyCustomerSession).toHaveBeenCalledWith();
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
      expect(getReadyCustomerSession).not.toHaveBeenCalled();
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

  it("does not navigate after invalid credentials and shows the specific message", async () => {
    signInWithPassword.mockResolvedValue({ error: { message: "Invalid login credentials" } });
    const user = userEvent.setup();
    render(
      <EmailForm locale="en" labels={labels} mode="login" portal="vendor" defaultNextPath="/en" />,
    );

    await submit(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
    expect(getReadyCustomerSession).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  it("sends an existing seven-character password to Auth during login", async () => {
    const user = userEvent.setup();
    render(
      <EmailForm locale="en" labels={labels} mode="login" portal="vendor" defaultNextPath="/en" />,
    );

    await user.type(screen.getByLabelText(/email address/i), "owner@example.com");
    await user.type(screen.getByLabelText(/password/i), "pass123");
    await user.click(screen.getByRole("button", { name: "Sign in with email" }));

    await waitFor(() => {
      expect(signInWithPassword).toHaveBeenCalledWith({
        email: "owner@example.com",
        password: "pass123",
      });
      expect(push).toHaveBeenCalledWith("/en");
    });
  });

  it("retains the eight-character minimum when creating an account", async () => {
    const user = userEvent.setup();
    render(
      <EmailForm
        locale="en"
        labels={{ ...labels, submit: "Create account" }}
        mode="signup"
        portal="customer"
        defaultNextPath="/en"
      />,
    );

    await user.type(screen.getByLabelText(/email address/i), "owner@example.com");
    await user.type(screen.getByLabelText(/password/i), "pass123");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Invalid password");
    expect(signUp).not.toHaveBeenCalled();
  });

  it("does not navigate when a customer session is absent after password sign in", async () => {
    getReadyCustomerSession.mockResolvedValue(null);
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

    expect(await screen.findByRole("alert")).toHaveTextContent("Generic error");
    expect(getPreferences).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  it("does not navigate after a rejected signup and reports the registration error", async () => {
    signUp.mockResolvedValue({ error: { message: "User already registered" } });
    const user = userEvent.setup();
    render(
      <EmailForm
        locale="en"
        labels={{ ...labels, submit: "Create account" }}
        mode="signup"
        portal="customer"
        defaultNextPath="/en"
      />,
    );

    await user.type(screen.getByLabelText(/email address/i), "owner@example.com");
    await user.type(screen.getByLabelText(/password/i), "password1");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Already registered");
    expect(signInWithPassword).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  it("shows confirmation instructions without navigating when signup has no session", async () => {
    signUp.mockResolvedValue({ data: { user: { id: "new-user" }, session: null }, error: null });
    const user = userEvent.setup();
    render(
      <EmailForm
        locale="en"
        labels={{ ...labels, submit: "Create account" }}
        mode="signup"
        portal="customer"
        defaultNextPath="/en"
      />,
    );

    await user.type(screen.getByLabelText(/email address/i), "owner@example.com");
    await user.type(screen.getByLabelText(/password/i), "password1");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("status")).toHaveTextContent(labels.signupConfirmation);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(getReadyCustomerSession).not.toHaveBeenCalled();
    expect(getPreferences).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  it("keeps immediate-session signup navigation when confirmation is disabled", async () => {
    const user = userEvent.setup();
    render(
      <EmailForm
        locale="en"
        labels={{ ...labels, submit: "Create account" }}
        mode="signup"
        portal="customer"
        defaultNextPath="/en"
      />,
    );

    await user.type(screen.getByLabelText(/email address/i), "owner@example.com");
    await user.type(screen.getByLabelText(/password/i), "password1");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => {
      expect(getReadyCustomerSession).toHaveBeenCalled();
      expect(push).toHaveBeenCalledWith("/en");
    });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows the same neutral confirmation status when signup returns no user or session", async () => {
    signUp.mockResolvedValue({ data: { user: null, session: null }, error: null });
    const user = userEvent.setup();
    render(
      <EmailForm
        locale="en"
        labels={{ ...labels, submit: "Create account" }}
        mode="signup"
        portal="customer"
        defaultNextPath="/en"
      />,
    );

    await user.type(screen.getByLabelText(/email address/i), "owner@example.com");
    await user.type(screen.getByLabelText(/password/i), "password1");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("status")).toHaveTextContent(labels.signupConfirmation);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(getReadyCustomerSession).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });
});
