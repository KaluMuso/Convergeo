// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// The sell-page CTAs must resolve their vendor link through the shared accessor,
// never through an inline localhost fallback.
vi.mock("./vendor-app", () => ({
  VENDOR_ONBOARDING_PATH: "/onboarding",
  getVendorSignupUrl: vi.fn(),
  getVendorPortalUrl: vi.fn(),
  getVendorLoginUrl: vi.fn(),
}));

import { Cta } from "./cta";
import { Hero } from "./hero";
import { getVendorLoginUrl, getVendorPortalUrl } from "./vendor-app";

const mockedGetVendorLoginUrl = vi.mocked(getVendorLoginUrl);
const mockedGetVendorPortalUrl = vi.mocked(getVendorPortalUrl);

// Identity translator: returns the key so assertions stay locale-agnostic.
const t = (key: string): string => key;

const LOGIN_URL = "https://vendor.vergeo5.com/en/login";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockedGetVendorPortalUrl.mockReturnValue(null);
});

describe("Cta links invited sellers to the vendor sign-in", () => {
  it("renders working links (never a disabled button) to the vendor login", () => {
    mockedGetVendorLoginUrl.mockReturnValue(LOGIN_URL);

    const { container } = render(<Cta locale="en" t={t} />);

    expect(mockedGetVendorLoginUrl).toHaveBeenCalledWith("en");
    const cta = screen.getByTestId("vendor-signup-cta");
    expect(cta.tagName).toBe("A");
    expect(cta).toHaveAttribute("href", LOGIN_URL);
    const invite = screen.getByTestId("vendor-cta-invite-signin-link");
    expect(invite.tagName).toBe("A");
    expect(invite).toHaveAttribute("href", LOGIN_URL);
    expect(invite).toHaveTextContent("cta.haveInviteSignIn");
    expect(container.querySelector("button[disabled]")).toBeNull();
    expect(container.innerHTML).not.toContain("localhost");
  });
});

describe("Hero links invited sellers to the vendor sign-in", () => {
  it("renders working primary and invite sign-in links", () => {
    mockedGetVendorLoginUrl.mockReturnValue(LOGIN_URL);

    const { container } = render(<Hero locale="en" t={t} />);

    const cta = screen.getByTestId("vendor-hero-cta");
    expect(cta.tagName).toBe("A");
    expect(cta).toHaveAttribute("href", LOGIN_URL);
    expect(screen.getByTestId("vendor-invite-signin-link")).toHaveAttribute("href", LOGIN_URL);
    expect(container.querySelector("button[disabled]")).toBeNull();
    expect(container.innerHTML).not.toContain("localhost");
  });
});
