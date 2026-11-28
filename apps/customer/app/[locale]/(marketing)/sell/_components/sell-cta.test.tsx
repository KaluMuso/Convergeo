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
  getVendorJoinUrl: vi.fn(),
}));

import { Cta } from "./cta";
import { Hero } from "./hero";
import { getVendorJoinUrl, getVendorLoginUrl, getVendorPortalUrl } from "./vendor-app";

const mockedGetVendorLoginUrl = vi.mocked(getVendorLoginUrl);
const mockedGetVendorJoinUrl = vi.mocked(getVendorJoinUrl);
const mockedGetVendorPortalUrl = vi.mocked(getVendorPortalUrl);

// Identity translator: returns the key so assertions stay locale-agnostic.
const t = (key: string): string => key;

const LOGIN_URL = "https://vendor.vergeo5.com/en/login";
const JOIN_URL = "https://vendor.vergeo5.com/en/signup";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockedGetVendorPortalUrl.mockReturnValue(null);
  mockedGetVendorJoinUrl.mockReturnValue(JOIN_URL);
});

describe("Cta sends new sellers to self-serve sign-up", () => {
  it("renders working links (never a disabled button) to sign-up and sign-in", () => {
    mockedGetVendorLoginUrl.mockReturnValue(LOGIN_URL);
    mockedGetVendorJoinUrl.mockReturnValue(JOIN_URL);

    const { container } = render(<Cta locale="en" t={t} />);

    expect(mockedGetVendorLoginUrl).toHaveBeenCalledWith("en");
    const cta = screen.getByTestId("vendor-signup-cta");
    expect(cta.tagName).toBe("A");
    expect(cta).toHaveAttribute("href", JOIN_URL);
    const signIn = screen.getByTestId("vendor-cta-signin-link");
    expect(signIn.tagName).toBe("A");
    expect(signIn).toHaveAttribute("href", LOGIN_URL);
    expect(signIn).toHaveTextContent("cta.haveAccountSignIn");
    expect(screen.queryByTestId("sell-invite-only-notice")).toBeNull();
    expect(container.querySelector("button[disabled]")).toBeNull();
    expect(container.innerHTML).not.toContain("localhost");
  });
});

describe("Hero sends new sellers to self-serve sign-up", () => {
  it("renders working sign-up and sign-in links", () => {
    mockedGetVendorLoginUrl.mockReturnValue(LOGIN_URL);
    mockedGetVendorJoinUrl.mockReturnValue(JOIN_URL);

    const { container } = render(<Hero locale="en" t={t} />);

    const cta = screen.getByTestId("vendor-hero-cta");
    expect(cta.tagName).toBe("A");
    expect(cta).toHaveAttribute("href", JOIN_URL);
    expect(screen.getByTestId("vendor-signin-link")).toHaveAttribute("href", LOGIN_URL);
    expect(screen.queryByTestId("sell-invite-only-notice")).toBeNull();
    expect(container.querySelector("button[disabled]")).toBeNull();
    expect(container.innerHTML).not.toContain("localhost");
  });
});
