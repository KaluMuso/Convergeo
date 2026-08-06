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

  it("fails closed in production without site URL", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "");
    expect(getCustomerAppUrl()).toBeNull();
    expect(getVendorStorefrontUrl("en", "shop")).toBeNull();
  });
});
