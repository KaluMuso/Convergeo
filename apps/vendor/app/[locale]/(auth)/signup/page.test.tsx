// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
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

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("next-intl/server", () => ({
  getMessages: vi.fn().mockResolvedValue({}),
  setRequestLocale: vi.fn(),
  // `@vergeo/i18n` calls this at module-import time to register its request
  // config (packages/i18n/src/request.ts) — never invoked directly by this
  // test, but it must exist on the mock or importing `@vergeo/i18n` throws.
  getRequestConfig: (fn: unknown) => fn,
}));

afterEach(() => {
  vi.unstubAllEnvs();
  cleanup();
  vi.clearAllMocks();
});

import VendorSignupPage from "./page";

/**
 * Start selling → sign-up → KYC: a new seller must be able to create an account
 * on the vendor app without an invite. Renders the real page and shell.
 */
describe("vendor signup page", () => {
  it("renders seller sign-up with phone creation and a way back to sign-in", async () => {
    vi.stubEnv("NEXT_PUBLIC_PHONE_OTP_ENABLED", "true");
    render(
      await VendorSignupPage({
        params: Promise.resolve({ locale: "en" }),
        searchParams: Promise.resolve({}),
      }),
    );

    expect(
      screen.getByRole("heading", { name: /create your seller account/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /phone|mobile/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/en/login");
  });

  it("offers email sign-up when phone OTP is off", async () => {
    vi.stubEnv("NEXT_PUBLIC_PHONE_OTP_ENABLED", "");
    render(
      await VendorSignupPage({
        params: Promise.resolve({ locale: "en" }),
        searchParams: Promise.resolve({}),
      }),
    );

    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create|sign up/i })).toBeInTheDocument();
  });

  it("renders nothing for an unknown locale", async () => {
    const out = await VendorSignupPage({
      params: Promise.resolve({ locale: "xx" }),
      searchParams: Promise.resolve({}),
    });
    expect(out).toBeNull();
  });
});
