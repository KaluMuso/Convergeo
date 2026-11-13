import { DEFAULT_LOCALE, LOCALES } from "@vergeo/i18n";
import { NextResponse } from "next/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next-intl/middleware", () => ({
  default: vi.fn(() => vi.fn(() => NextResponse.next())),
}));

import { config, isCheckoutCardRoute } from "./middleware";

describe("customer middleware matcher", () => {
  it("keeps the CSP report path and the broadened locale-redirect matcher", () => {
    expect(config.matcher).toEqual(["/api/csp-report", "/((?!api|_next|_vercel|.*\\..*).*)"]);
  });

  it("matches locale-less app paths so next-intl can redirect them (regression: a bare path like `/cart` or `/sw.js` used to skip the redirect, land on `/[locale]` with an invalid locale value, and throw formatting any interpolated message — INVALID_MESSAGE in production)", () => {
    const pattern = new RegExp(`^${config.matcher[1]}$`);
    expect(pattern.test("/cart")).toBe(true);
    expect(pattern.test("/wishlist")).toBe(true);
    expect(pattern.test("/en/cart")).toBe(true);
  });

  it("still excludes Next internals, other API routes, and static files with an extension", () => {
    const pattern = new RegExp(`^${config.matcher[1]}$`);
    expect(pattern.test("/api/csp-report")).toBe(false);
    expect(pattern.test("/_next/static/chunk.js")).toBe(false);
    expect(pattern.test("/favicon.ico")).toBe(false);
  });
});

describe("customer locale routing", () => {
  it("redirect contract points / to /en", () => {
    expect(`/${DEFAULT_LOCALE}`).toBe("/en");
  });

  it("supports en and fr locale switch targets", () => {
    expect(LOCALES).toContain("en");
    expect(LOCALES).toContain("fr");
  });

  it("treats unknown locale codes as unsupported", () => {
    expect(LOCALES.includes("zz" as (typeof LOCALES)[number])).toBe(false);
  });
});

describe("customer CSP route gates", () => {
  it("allows the Lenco CSP only on localized checkout card routes", () => {
    expect(isCheckoutCardRoute("/en/checkout/card/pay_123")).toBe(true);
    expect(isCheckoutCardRoute("/bem/checkout/card/pay_123")).toBe(true);
    expect(isCheckoutCardRoute("/en/checkout")).toBe(false);
    expect(isCheckoutCardRoute("/en/checkout/card/pay_123/extra")).toBe(false);
    expect(isCheckoutCardRoute("/zz/checkout/card/pay_123")).toBe(false);
  });
});
