import { describe, expect, it } from "vitest";

import {
  buildConnectSrc,
  isDevelopmentEnv,
  PERMISSIONS_POLICY_ADMIN,
  PERMISSIONS_POLICY_CUSTOMER,
  PERMISSIONS_POLICY_DEFAULT,
  resolveApiConnectOrigins,
} from "./security-headers";

describe("security-headers", () => {
  it("includes localhost API in development", () => {
    const origins = resolveApiConnectOrigins({
      NODE_ENV: "development",
      NEXT_PUBLIC_API_BASE_URL: "http://localhost:8000",
    });
    expect(origins).toContain("http://localhost:8000");
    expect(origins).toContain("https://api.vergeo5.com");
  });

  it("omits localhost API in production", () => {
    const origins = resolveApiConnectOrigins({
      NODE_ENV: "production",
      NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
    });
    expect(origins).not.toContain("http://localhost:8000");
    expect(origins).toContain("https://api.vergeo5.com");
    expect(origins).toContain("https://api.staging.vergeo5.com");
  });

  it("buildConnectSrc includes API and Supabase", () => {
    const directive = buildConnectSrc({
      NODE_ENV: "production",
      NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
    });
    expect(directive).toContain("'self'");
    expect(directive).toContain("https://api.vergeo5.com");
    expect(directive).toContain("https://*.supabase.co");
    expect(directive).toContain("wss://*.supabase.co");
  });

  it("buildConnectSrc adds Vercel origins outside development", () => {
    const prod = buildConnectSrc({ NODE_ENV: "production" });
    expect(prod).toContain("https://*.vercel.app");

    const dev = buildConnectSrc({ NODE_ENV: "development" });
    expect(dev).not.toContain("https://*.vercel.app");
  });

  it("lets only the customer storefront use its own microphone (Ask Vergeo voice)", () => {
    expect(PERMISSIONS_POLICY_CUSTOMER).toContain("microphone=(self)");
    expect(PERMISSIONS_POLICY_CUSTOMER).toContain("camera=()");
    expect(PERMISSIONS_POLICY_CUSTOMER).not.toContain("microphone=*");
    expect(PERMISSIONS_POLICY_DEFAULT).toContain("microphone=()");
    expect(PERMISSIONS_POLICY_ADMIN).toContain("microphone=()");
  });

  it("detects development env", () => {
    expect(isDevelopmentEnv({ NODE_ENV: "development" })).toBe(true);
    expect(isDevelopmentEnv({ NODE_ENV: "production" })).toBe(false);
    expect(isDevelopmentEnv({ NODE_ENV: "test" })).toBe(true);
  });
});
