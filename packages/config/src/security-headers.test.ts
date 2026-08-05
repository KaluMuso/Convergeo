import { describe, expect, it } from "vitest";

import { buildConnectSrc, isDevelopmentEnv, resolveApiConnectOrigins } from "./security-headers";

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

  it("detects development env", () => {
    expect(isDevelopmentEnv({ NODE_ENV: "development" })).toBe(true);
    expect(isDevelopmentEnv({ NODE_ENV: "production" })).toBe(false);
    expect(isDevelopmentEnv({ NODE_ENV: "test" })).toBe(true);
  });
});
