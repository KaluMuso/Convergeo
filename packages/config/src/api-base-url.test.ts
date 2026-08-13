import { describe, expect, it } from "vitest";

import {
  isDeployedFrontendEnv,
  isLoopbackApiOrigin,
  isProductionApiOrigin,
  resolvePublicApiBaseUrl,
} from "./api-base-url";

describe("loopback and production API origin detection", () => {
  it("detects localhost, loopback, and IPv6 loopback", () => {
    expect(isLoopbackApiOrigin("http://localhost:8000")).toBe(true);
    expect(isLoopbackApiOrigin("http://127.0.0.1:8000")).toBe(true);
    expect(isLoopbackApiOrigin("http://[::1]:8000")).toBe(true);
    expect(isLoopbackApiOrigin("http://foo.localhost:8000")).toBe(true);
    expect(isLoopbackApiOrigin("https://api.vergeo5.com")).toBe(false);
    expect(isLoopbackApiOrigin("https://api.staging.vergeo5.com")).toBe(false);
  });

  it("detects the production API host", () => {
    expect(isProductionApiOrigin("https://api.vergeo5.com")).toBe(true);
    expect(isProductionApiOrigin("https://api.vergeo5.com/v1")).toBe(true);
    expect(isProductionApiOrigin("https://api.staging.vergeo5.com")).toBe(false);
  });
});

describe("resolvePublicApiBaseUrl", () => {
  it("returns the configured origin without a trailing slash", () => {
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com/",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.vergeo5.com");
  });

  it("never falls back to localhost in production when unset", () => {
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "",
        NODE_ENV: "production",
      }),
    ).toBeNull();
    expect(resolvePublicApiBaseUrl({ NODE_ENV: "production" })).toBeNull();
  });

  it("rejects an explicit loopback URL in production and Vercel preview", () => {
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "http://localhost:8000",
        NODE_ENV: "production",
      }),
    ).toBeNull();
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000",
        VERCEL_ENV: "preview",
        NODE_ENV: "production",
      }),
    ).toBeNull();
  });

  it("rejects a staging Preview that points at the production API", () => {
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
        VERCEL_ENV: "preview",
        NODE_ENV: "production",
      }),
    ).toBeNull();
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "https://api.staging.vergeo5.com",
        VERCEL_ENV: "preview",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.staging.vergeo5.com");
  });

  it("allows the production API only on the production Vercel target", () => {
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
        VERCEL_ENV: "production",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.vergeo5.com");
  });

  it("uses the local FastAPI default in development when unset", () => {
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: undefined,
        NODE_ENV: "development",
      }),
    ).toBe("http://localhost:8000");
  });

  it("reads the admin-specific public env key when requested", () => {
    expect(
      resolvePublicApiBaseUrl(
        {
          NEXT_PUBLIC_VERGEO_API_URL: "https://api.staging.vergeo5.com/",
          NODE_ENV: "production",
        },
        ["NEXT_PUBLIC_VERGEO_API_URL"],
      ),
    ).toBe("https://api.staging.vergeo5.com");
  });

  it("treats Vercel production/preview as deployed even if NODE_ENV is omitted", () => {
    expect(isDeployedFrontendEnv({ VERCEL_ENV: "preview" })).toBe(true);
    expect(isDeployedFrontendEnv({ VERCEL_ENV: "production" })).toBe(true);
    expect(isDeployedFrontendEnv({ VERCEL_ENV: "development", NODE_ENV: "development" })).toBe(
      false,
    );
  });
});
