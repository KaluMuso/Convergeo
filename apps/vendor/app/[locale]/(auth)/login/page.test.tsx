// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  cleanup();
  vi.clearAllMocks();
});

import VendorLoginPage from "./page";

/**
 * PR-D root cause: this page previously passed `phoneEnabled={false}` to the
 * shared `AuthLoginShell`, so Vendor had NO UI path to phone-OTP login even
 * though certification config (E2E_VENDOR_TEST_PHONE/OTP) and the seed
 * contract already assumed one existed. Renders the REAL page (real
 * `@vergeo/i18n` messages, real `AuthLoginShell`/`PhoneForm`/`EmailForm`) so a
 * future revert of the `phoneEnabled` prop fails this test, not just a
 * shell-level unit test that never touches the actual page wiring.
 */
describe("vendor login page", () => {
  it("renders phone login by default and keeps email/password reachable via toggle", async () => {
    const user = userEvent.setup();
    render(
      await VendorLoginPage({
        params: Promise.resolve({ locale: "en" }),
        searchParams: Promise.resolve({}),
      }),
    );

    expect(screen.getByRole("textbox", { name: /phone|mobile/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/email address/i)).not.toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: /use email instead/i });
    await user.click(toggle);

    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
  });

  it("renders no signup link", async () => {
    render(
      await VendorLoginPage({
        params: Promise.resolve({ locale: "en" }),
        searchParams: Promise.resolve({}),
      }),
    );

    expect(
      screen.queryByRole("link", { name: /create an account|sign up/i }),
    ).not.toBeInTheDocument();
  });
});
