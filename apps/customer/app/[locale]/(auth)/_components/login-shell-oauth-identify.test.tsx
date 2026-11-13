// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const SESSION_KEY_V2 = "vg_sess2";
const SESSION = "33333333-3333-4333-8333-333333333333";

const exchangeCodeForSession = vi.fn(async () => ({ error: null }));
const getSession = vi.fn(async () => ({ data: { session: { access_token: "google-jwt" } } }));

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: {
      exchangeCodeForSession,
      getSession,
      signInWithOtp: vi.fn(),
      verifyOtp: vi.fn(),
      signInWithPassword: vi.fn(),
      signUp: vi.fn(),
    },
  }),
}));

// Post-auth navigation reads the session through the customer-session helper (cart merge
// barrier); it resolves to the same Google session token the exchange produced.
vi.mock("../../../../lib/customer-session", () => ({
  getReadyCustomerSession: async () => ({ access_token: "google-jwt" }),
}));

vi.mock("../../account/_components/account-api", () => ({
  createAccountApiClient: () => ({
    getPreferences: async () => ({ onboarding: { completed_at: "2026-08-13T00:00:00Z" } }),
  }),
}));

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
}));

import { AuthLoginShell } from "./login-shell";

import type { AuthLoginLabels } from "./login-shell";

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

let fetchMock: ReturnType<typeof vi.fn>;

function identifyCalls(): unknown[][] {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/analytics/identify"));
}

async function completeGoogleCallback(): Promise<void> {
  window.history.pushState({}, "", "/en/login?code=oauth-code&next=%2Fen");
  render(<AuthLoginShell locale="en" variant="customer" labels={labels} defaultNextPath="/en" />);
  await vi.waitFor(() => expect(push).toHaveBeenCalled());
  // let the lazy identify import settle
  await new Promise((resolve) => setTimeout(resolve, 20));
}

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_ANALYTICS_V2_TRACKING", "1");
  window.localStorage.clear();
  document.cookie = "vg_analytics_consent=; path=/; max-age=0";
  Object.defineProperty(navigator, "globalPrivacyControl", {
    configurable: true,
    value: undefined,
  });
  window.localStorage.setItem(
    SESSION_KEY_V2,
    JSON.stringify({ id: SESSION, last: Date.now(), seq: 1 }),
  );
  fetchMock = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("Google OAuth callback links the analytics session", () => {
  it("calls identify once with the Google session token", async () => {
    await completeGoogleCallback();
    expect(exchangeCodeForSession).toHaveBeenCalledWith("oauth-code");
    const calls = identifyCalls();
    expect(calls).toHaveLength(1);
    expect(JSON.parse((calls[0]![1] as RequestInit).body as string)).toEqual({
      session_id: SESSION,
    });
    expect((calls[0]![1] as { headers: Record<string, string> }).headers.Authorization).toBe(
      "Bearer google-jwt",
    );
  });

  it("sends nothing when the visitor opted out", async () => {
    document.cookie = "vg_analytics_consent=denied; path=/";
    await completeGoogleCallback();
    expect(identifyCalls()).toHaveLength(0);
  });

  it("sends nothing under Global Privacy Control", async () => {
    Object.defineProperty(navigator, "globalPrivacyControl", { configurable: true, value: true });
    await completeGoogleCallback();
    expect(identifyCalls()).toHaveLength(0);
  });

  it("does not re-send for a session that is already linked", async () => {
    window.localStorage.setItem("vg_ident2", SESSION);
    await completeGoogleCallback();
    expect(identifyCalls()).toHaveLength(0);
  });
});
