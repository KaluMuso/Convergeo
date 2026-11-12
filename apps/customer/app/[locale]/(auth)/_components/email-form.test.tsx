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
const getClient = vi.fn();

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: () => getClient(),
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
  network: "Check your connection and try again.",
  unavailable: "Sign-in is temporarily unavailable.",
};

describe("EmailForm portal post-auth", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    getClient.mockResolvedValue({ auth: { signInWithPassword, signUp, getSession } });
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

  it.each(["customer", "vendor", "admin"] as const)(
    "%s maps a structured credential rejection without raw response output",
    async (portal) => {
      signInWithPassword.mockResolvedValue({
        error: { code: "invalid_credentials", status: 400, message: "private provider details" },
      });
      render(
        <EmailForm
          locale="en"
          labels={labels}
          mode="login"
          portal={portal}
          defaultNextPath="/en"
        />,
      );
      await submit(userEvent.setup());
      expect(screen.getByRole("alert")).toHaveTextContent(labels.invalidCredentials);
      expect(push).not.toHaveBeenCalled();
      expect(getPreferences).not.toHaveBeenCalled();
      expect(console.warn).toHaveBeenCalledWith("auth_failure", {
        stage: "authenticate",
        portal,
        mode: "login",
        category: "invalid_credentials",
        httpStatus: 400,
      });
    },
  );

  it.each([
    [{ code: "over_request_rate_limit", status: 429 }, "Try again in 60 seconds", "throttled"],
    [
      { name: "AuthRetryableFetchError", status: 0, message: "raw network details" },
      labels.network,
      "network",
    ],
    [{ status: 503, message: "raw server details" }, labels.unavailable, "service_unavailable"],
    [
      {
        code: "unknown_private_code",
        message: "invalid login credentials private@example.com secret-token",
      },
      labels.generic,
      "generic",
    ],
    [
      { code: "user_not_found", message: "private account state" },
      labels.invalidCredentials,
      "invalid_credentials",
    ],
  ] as const)("maps vendor auth failure safely: %j", async (error, expected, category) => {
    signInWithPassword.mockResolvedValue({ error });
    render(
      <EmailForm locale="en" labels={labels} mode="login" portal="vendor" defaultNextPath="/en" />,
    );
    await submit(userEvent.setup());
    expect(screen.getByRole("alert")).toHaveTextContent(expected);
    expect(push).not.toHaveBeenCalled();
    expect(getPreferences).not.toHaveBeenCalled();
    const output = JSON.stringify(vi.mocked(console.warn).mock.calls);
    expect(output).toContain(category);
    expect(output).not.toMatch(
      /private|raw|secret-token|password1|owner@example|unknown_private_code/,
    );
  });

  it("distinguishes initialization failure without exposing the missing variable or key", async () => {
    getClient.mockRejectedValue(new Error("NEXT_PUBLIC_SUPABASE_ANON_KEY=private-key"));
    render(
      <EmailForm locale="en" labels={labels} mode="login" portal="vendor" defaultNextPath="/en" />,
    );
    await submit(userEvent.setup());
    expect(screen.getByRole("alert")).toHaveTextContent(labels.unavailable);
    expect(signInWithPassword).not.toHaveBeenCalled();
    expect(console.warn).toHaveBeenCalledWith("auth_failure", {
      stage: "initialize",
      portal: "vendor",
      mode: "login",
      category: "client_unavailable",
    });
  });

  it("maps thrown transport errors and remains retryable", async () => {
    signInWithPassword.mockRejectedValueOnce(new TypeError("Failed to fetch private-url"));
    render(
      <EmailForm locale="en" labels={labels} mode="login" portal="vendor" defaultNextPath="/en" />,
    );
    const user = userEvent.setup();
    await submit(user);
    expect(screen.getByRole("alert")).toHaveTextContent(labels.network);
    expect(screen.getByRole("button", { name: labels.submit })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: labels.submit }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/en"));
  });

  it("distinguishes navigation failure after successful authentication", async () => {
    push.mockImplementationOnce(() => {
      throw new Error("private navigation URL");
    });
    render(
      <EmailForm locale="en" labels={labels} mode="login" portal="vendor" defaultNextPath="/en" />,
    );
    await submit(userEvent.setup());
    expect(screen.getByRole("alert")).toHaveTextContent(labels.generic);
    expect(console.warn).toHaveBeenCalledWith("auth_failure", {
      stage: "navigate",
      portal: "vendor",
      mode: "login",
      category: "generic",
    });
  });

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
