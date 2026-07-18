import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getVendorAppUrl,
  getVendorSignupUrl,
  isVendorAppConfigured,
  VENDOR_ONBOARDING_PATH,
} from "./vendor-app";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("getVendorSignupUrl (configured)", () => {
  it("builds a locale-aware signup URL from the configured vendor app URL", () => {
    vi.stubEnv("NEXT_PUBLIC_VENDOR_APP_URL", "https://vendor.vergeo5.com");

    expect(VENDOR_ONBOARDING_PATH).toBe("/onboarding");
    expect(getVendorSignupUrl("en")).toBe("https://vendor.vergeo5.com/en/onboarding");
    expect(getVendorSignupUrl("bem")).toBe("https://vendor.vergeo5.com/bem/onboarding");
    expect(getVendorSignupUrl("fr")).toBe("https://vendor.vergeo5.com/fr/onboarding");
    expect(isVendorAppConfigured()).toBe(true);
  });

  it("normalises a trailing slash on the configured URL", () => {
    vi.stubEnv("NEXT_PUBLIC_VENDOR_APP_URL", "https://vendor.vergeo5.com/");

    expect(getVendorSignupUrl("en")).toBe("https://vendor.vergeo5.com/en/onboarding");
  });

  it("honours the configured URL even in a production build", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_VENDOR_APP_URL", "https://vendor.vergeo5.com");

    expect(getVendorSignupUrl("en")).toBe("https://vendor.vergeo5.com/en/onboarding");
  });
});

describe("fail closed in production", () => {
  it("never emits localhost:3001 when the vendor URL is absent in a production build", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_VENDOR_APP_URL", "");

    expect(getVendorAppUrl()).toBeNull();
    expect(getVendorSignupUrl("en")).toBeNull();
    expect(isVendorAppConfigured()).toBe(false);
    expect(String(getVendorSignupUrl("en"))).not.toContain("localhost:3001");
  });

  it("fails closed for an invalid vendor URL in a production build", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_VENDOR_APP_URL", "not-a-valid-url");

    expect(getVendorSignupUrl("en")).toBeNull();
  });

  it("fails closed for a non-http(s) scheme in a production build", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_VENDOR_APP_URL", "ftp://vendor.vergeo5.com");

    expect(getVendorSignupUrl("en")).toBeNull();
  });
});

describe("development fallback", () => {
  it("falls back to the local vendor dev server outside production", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_VENDOR_APP_URL", "");

    expect(getVendorSignupUrl("en")).toBe("http://localhost:3001/en/onboarding");
    expect(getVendorSignupUrl("bem")).toBe("http://localhost:3001/bem/onboarding");
  });
});
