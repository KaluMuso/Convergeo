import { describe, expect, it } from "vitest";

import { absoluteApiUrl, getApiBaseUrl, resolveApiBaseUrl } from "./api-base-url";

describe("resolveApiBaseUrl", () => {
  it("returns the configured origin without a trailing slash", () => {
    expect(
      resolveApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com/",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.vergeo5.com");
  });

  it("defaults to the production API on the production plane when unset", () => {
    expect(
      resolveApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.vergeo5.com");
    expect(
      getApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.vergeo5.com");
  });

  it("never infers a loopback origin when the plane is missing", () => {
    expect(
      resolveApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: undefined,
        NODE_ENV: "development",
      }),
    ).toBeNull();
  });
});

describe("absoluteApiUrl", () => {
  it("joins base + path and never returns a relative URL", () => {
    expect(
      absoluteApiUrl("/events/zed-summer-festival", {
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com/",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.vergeo5.com/events/zed-summer-festival");
  });

  it("returns null when the plane is unset (SSG-safe fail-closed)", () => {
    expect(
      absoluteApiUrl("/events/zed-summer-festival", {
        NEXT_PUBLIC_API_BASE_URL: "",
        NODE_ENV: "production",
      }),
    ).toBeNull();
  });
});

describe("localhost is impossible in a production browser build", () => {
  type ApiEnvBag = {
    NEXT_PUBLIC_API_BASE_URL?: string;
    NEXT_PUBLIC_DEPLOYMENT_PLANE?: string;
    NODE_ENV?: string;
  };

  const productionCases: Array<[string, ApiEnvBag]> = [
    ["var entirely absent", { NODE_ENV: "production" }],
    ["var undefined", { NEXT_PUBLIC_API_BASE_URL: undefined, NODE_ENV: "production" }],
    ["var empty string", { NEXT_PUBLIC_API_BASE_URL: "", NODE_ENV: "production" }],
    ["var whitespace only", { NEXT_PUBLIC_API_BASE_URL: "   ", NODE_ENV: "production" }],
  ];

  for (const [label, bag] of productionCases) {
    it(`fails closed and never yields a loopback origin — ${label}`, () => {
      expect(resolveApiBaseUrl(bag)).toBeNull();
      expect(getApiBaseUrl(bag)).toBe("");
      expect(getApiBaseUrl(bag)).not.toMatch(/127\.0\.0\.1|\[::1\]/);
      expect(absoluteApiUrl("/cart", bag)).toBeNull();
    });
  }

  it("only emits the loopback default on an explicit development plane", () => {
    expect(
      resolveApiBaseUrl({
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "development",
        NODE_ENV: "development",
      }),
    ).toBe("http://localhost:8000");
    expect(resolveApiBaseUrl({ NODE_ENV: "test" })).toBeNull();
  });

  it("rejects loopback and production-API-on-preview even when explicitly configured", () => {
    expect(
      resolveApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "http://localhost:8000",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NODE_ENV: "production",
      }),
    ).toBeNull();
    expect(
      resolveApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "preview",
        NODE_ENV: "production",
      }),
    ).toBeNull();
  });
});
