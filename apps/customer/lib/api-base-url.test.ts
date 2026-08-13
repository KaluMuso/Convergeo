import { describe, expect, it } from "vitest";

import { absoluteApiUrl, getApiBaseUrl, resolveApiBaseUrl } from "./api-base-url";

describe("resolveApiBaseUrl", () => {
  it("returns the configured origin without a trailing slash", () => {
    expect(
      resolveApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com/",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.vergeo5.com");
  });

  it("never falls back to localhost in production when unset", () => {
    expect(
      resolveApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "",
        NODE_ENV: "production",
      }),
    ).toBeNull();
    expect(getApiBaseUrl({ NEXT_PUBLIC_API_BASE_URL: "", NODE_ENV: "production" })).toBe("");
  });

  it("uses the local FastAPI default in development when unset", () => {
    expect(
      resolveApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: undefined,
        NODE_ENV: "development",
      }),
    ).toBe("http://localhost:8000");
  });
});

describe("absoluteApiUrl", () => {
  it("joins base + path and never returns a relative URL", () => {
    expect(
      absoluteApiUrl("/events/zed-summer-festival", {
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com/",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.vergeo5.com/events/zed-summer-festival");
  });

  it("returns null when production base is unset (SSG-safe fail-closed)", () => {
    expect(
      absoluteApiUrl("/events/zed-summer-festival", {
        NEXT_PUBLIC_API_BASE_URL: "",
        NODE_ENV: "production",
      }),
    ).toBeNull();
  });
});

// Acceptance guard: a production browser build must never silently call localhost.
//
// `NEXT_PUBLIC_API_BASE_URL` and `NODE_ENV` are inlined at `next build`, and a
// Vercel production build always compiles with `NODE_ENV=production`. Every one
// of these bags models that build with the var absent/blank in some way; the
// resolver must fail closed (never a loopback origin) so the shipped bundle
// cannot bake `http://localhost:8000` into cart / search / PDP / checkout fetches.
describe("localhost is impossible in a production browser build", () => {
  type ApiEnvBag = { NEXT_PUBLIC_API_BASE_URL?: string; NODE_ENV?: string };

  const productionCases: Array<[string, ApiEnvBag]> = [
    ["var entirely absent", { NODE_ENV: "production" }],
    ["var undefined", { NEXT_PUBLIC_API_BASE_URL: undefined, NODE_ENV: "production" }],
    ["var empty string", { NEXT_PUBLIC_API_BASE_URL: "", NODE_ENV: "production" }],
    ["var whitespace only", { NEXT_PUBLIC_API_BASE_URL: "   ", NODE_ENV: "production" }],
  ];

  for (const [label, bag] of productionCases) {
    it(`fails closed and never yields localhost — ${label}`, () => {
      // resolveApiBaseUrl -> null; getApiBaseUrl -> "" (relative, same-origin);
      // absoluteApiUrl -> null so callers skip the fetch instead of hitting a loopback.
      expect(resolveApiBaseUrl(bag)).toBeNull();
      expect(getApiBaseUrl(bag)).toBe("");
      expect(getApiBaseUrl(bag)).not.toMatch(/localhost|127\.0\.0\.1/);
      expect(absoluteApiUrl("/cart", bag)).toBeNull();
      expect(absoluteApiUrl("/cart", bag) ?? "").not.toMatch(/localhost|127\.0\.0\.1/);
    });
  }

  it("only emits the loopback default outside a production build", () => {
    // The single audited dev convenience — reachable ONLY when NODE_ENV !== production,
    // which `next build` never produces.
    expect(resolveApiBaseUrl({ NODE_ENV: "development" })).toBe("http://localhost:8000");
    expect(resolveApiBaseUrl({ NODE_ENV: "test" })).toBe("http://localhost:8000");
  });

  it("rejects loopback and production-API-on-preview even when explicitly configured", () => {
    expect(
      resolveApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "http://localhost:8000",
        NODE_ENV: "production",
      }),
    ).toBeNull();
    expect(
      resolveApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
        VERCEL_ENV: "preview",
        NODE_ENV: "production",
      }),
    ).toBeNull();
  });
});
