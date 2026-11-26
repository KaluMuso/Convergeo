import { afterEach, describe, expect, it, vi } from "vitest";

import { getCustomerAppUrl, getVendorStorefrontUrl } from "./customer-app";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("customer-app", () => {
  it("uses configured site URL in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "https://vergeo5.com/");
    expect(getCustomerAppUrl()).toBe("https://vergeo5.com");
    expect(getVendorStorefrontUrl("en", "lusaka-electronics")).toBe(
      "https://vergeo5.com/en/v/lusaka-electronics",
    );
  });

  it("falls back to the public customer origin in production without site URL", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "");
    expect(getCustomerAppUrl()).toBe("https://www.vergeo5.com");
    expect(getVendorStorefrontUrl("en", "shop")).toBe("https://www.vergeo5.com/en/v/shop");
  });
});
