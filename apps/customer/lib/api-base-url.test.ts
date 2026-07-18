import { afterEach, describe, expect, it } from "vitest";

import { getApiBaseUrl, resolveApiBaseUrl } from "./api-base-url";

afterEach(() => {
  // no shared stubs — each test passes an explicit env bag
});

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
