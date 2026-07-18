// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// The sell-page CTAs must resolve their vendor link through the shared accessor,
// never through an inline localhost fallback. Mocking it lets us drive both the
// configured and fail-closed states deterministically.
vi.mock("./vendor-app", () => ({
  VENDOR_ONBOARDING_PATH: "/onboarding",
  getVendorSignupUrl: vi.fn(),
}));

import { Cta } from "./cta";
import { Hero } from "./hero";
import { getVendorSignupUrl } from "./vendor-app";

const mockedGetVendorSignupUrl = vi.mocked(getVendorSignupUrl);

// Identity translator: returns the key so assertions stay locale-agnostic.
const t = (key: string): string => key;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const SIGNUP_URL = "https://vendor.vergeo5.com/en/onboarding";

describe("Cta uses the shared vendor accessor", () => {
  it("links to the accessor's locale-aware signup URL when configured", () => {
    mockedGetVendorSignupUrl.mockReturnValue(SIGNUP_URL);

    render(<Cta locale="en" t={t} />);

    expect(mockedGetVendorSignupUrl).toHaveBeenCalledWith("en");
    const cta = screen.getByTestId("vendor-signup-cta");
    expect(cta.tagName).toBe("A");
    expect(cta).toHaveAttribute("href", SIGNUP_URL);
  });

  it("renders a disabled, explained CTA (no localhost) when the accessor fails closed", () => {
    mockedGetVendorSignupUrl.mockReturnValue(null);

    const { container } = render(<Cta locale="en" t={t} />);

    const cta = screen.getByTestId("vendor-signup-cta");
    expect(cta.tagName).toBe("BUTTON");
    expect(cta).toBeDisabled();
    expect(cta).toHaveAttribute("aria-disabled", "true");
    expect(cta).toHaveAttribute("aria-describedby", "cta-vendor-signup-unavailable");
    expect(container.querySelector("#cta-vendor-signup-unavailable")).toHaveTextContent(
      "signupUnavailable",
    );
    expect(container.querySelector("a[href*='localhost']")).toBeNull();
    expect(container.innerHTML).not.toContain("localhost:3001");
  });
});

describe("Hero uses the shared vendor accessor", () => {
  it("links to the accessor's locale-aware signup URL when configured", () => {
    mockedGetVendorSignupUrl.mockReturnValue(SIGNUP_URL);

    render(<Hero locale="en" t={t} />);

    expect(mockedGetVendorSignupUrl).toHaveBeenCalledWith("en");
    const cta = screen.getByTestId("vendor-hero-cta");
    expect(cta.tagName).toBe("A");
    expect(cta).toHaveAttribute("href", SIGNUP_URL);
  });

  it("renders a disabled, explained CTA (no localhost) when the accessor fails closed", () => {
    mockedGetVendorSignupUrl.mockReturnValue(null);

    const { container } = render(<Hero locale="en" t={t} />);

    const cta = screen.getByTestId("vendor-hero-cta");
    expect(cta.tagName).toBe("BUTTON");
    expect(cta).toBeDisabled();
    expect(cta).toHaveAttribute("aria-disabled", "true");
    expect(cta).toHaveAttribute("aria-describedby", "hero-vendor-signup-unavailable");
    expect(container.querySelector("#hero-vendor-signup-unavailable")).toHaveTextContent(
      "signupUnavailable",
    );
    expect(container.querySelector("a[href*='localhost']")).toBeNull();
    expect(container.innerHTML).not.toContain("localhost:3001");
  });
});
