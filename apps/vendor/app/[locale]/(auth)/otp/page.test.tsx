// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { redirectMock } = vi.hoisted(() => ({
  redirectMock: vi.fn((path: string) => {
    throw new Error(`NEXT_REDIRECT:${path}`);
  }),
}));

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));

vi.mock("next-intl/server", () => ({
  getMessages: vi.fn().mockResolvedValue({}),
  setRequestLocale: vi.fn(),
  // `@vergeo/i18n` calls this at module-import time to register its request
  // config (packages/i18n/src/request.ts) — never invoked directly by this
  // test, but it must exist on the mock or importing `@vergeo/i18n` throws.
  getRequestConfig: (fn: unknown) => fn,
}));

// Captures the exact props reaching the shared OtpForm — the direct proof
// that this route wires `portal="vendor"` (so verifyOtp never touches
// Customer's onboarding/preferences path — see post-auth-navigation.ts) and
// never invents a Vendor-specific Supabase verification implementation of
// its own.
const { otpFormPropsCalls } = vi.hoisted(() => ({ otpFormPropsCalls: [] as unknown[] }));
vi.mock("../../../../../customer/app/[locale]/(auth)/_components/otp-form", () => ({
  OtpForm: (props: unknown) => {
    otpFormPropsCalls.push(props);
    return null;
  },
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  otpFormPropsCalls.length = 0;
});

import VendorOtpPage from "./page";

describe("vendor otp page", () => {
  it("redirects to Vendor /login when the phone query param is missing", async () => {
    await expect(
      VendorOtpPage({
        params: Promise.resolve({ locale: "en" }),
        searchParams: Promise.resolve({}),
      }),
    ).rejects.toThrow("NEXT_REDIRECT:/en/login");

    expect(redirectMock).toHaveBeenCalledWith("/en/login");
  });

  it("renders OtpForm with portal=vendor, the Vendor login as change-phone destination, and a Vendor fallback route", async () => {
    render(
      await VendorOtpPage({
        params: Promise.resolve({ locale: "en" }),
        searchParams: Promise.resolve({ phone: "+260970000004" }),
      }),
    );

    expect(otpFormPropsCalls).toHaveLength(1);
    const props = otpFormPropsCalls[0] as Record<string, unknown>;
    expect(props.portal).toBe("vendor");
    expect(props.loginPath).toBe("/login");
    expect(props.defaultNextPath).toBe("/en");
    expect(props.phone).toBe("+260970000004");
    expect(props.locale).toBe("en");
  });

  it("masks the phone number in the rendered copy", async () => {
    render(
      await VendorOtpPage({
        params: Promise.resolve({ locale: "en" }),
        searchParams: Promise.resolve({ phone: "+260970000004" }),
      }),
    );

    expect(screen.queryByText("+260970000004")).not.toBeInTheDocument();
    expect(screen.getByText(/\+260 ••• ••004/)).toBeInTheDocument();
  });

  it("preserves a sanitized next param through to OtpForm", async () => {
    render(
      await VendorOtpPage({
        params: Promise.resolve({ locale: "en" }),
        searchParams: Promise.resolve({ phone: "+260970000004", next: "/en/services" }),
      }),
    );

    const props = otpFormPropsCalls[0] as Record<string, unknown>;
    expect(props.nextParam).toBe("/en/services");
  });
});
