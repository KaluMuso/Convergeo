import { DEFAULT_LOCALE, LOCALES } from "@vergeo/i18n";
import { NextResponse } from "next/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next-intl/middleware", () => ({
  default: vi.fn(() => vi.fn(() => NextResponse.next())),
}));

import { isCheckoutCardRoute } from "./middleware";

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
